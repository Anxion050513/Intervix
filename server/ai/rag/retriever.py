"""Hybrid retriever — Dense (ChromaDB) + BM25 sparse with RRF fusion.

Pipeline:
    1. Dense retrieval via ChromaDB embedding similarity  → top-k_dense
    2. BM25 sparse retrieval via keyword scoring           → top-k_sparse
    3. Weighted RRF (Reciprocal Rank Fusion)               → merged ranking
"""

import logging
from typing import Any

from langchain_core.documents import Document

from server.ai.rag.vector_store import get_or_create_collection
from server.ai.rag.embedder import get_embedder
from server.ai.rag.bm25 import BM25Index

logger = logging.getLogger(__name__)

# Default RRF parameter — controls how much rank position matters.
# Higher k → all ranks contribute more equally; lower k → top ranks dominate.
RRF_K = 60

# Default hybrid weights (Dense : BM25).
DEFAULT_DENSE_WEIGHT = 0.7
DEFAULT_SPARSE_WEIGHT = 0.3


def _rrf_score(rank: int, k: int = RRF_K) -> float:
    """Compute RRF score for a single ranked item.

    RRF(d) = 1 / (k + rank)    where rank is 0-indexed.
    """
    return 1.0 / (k + rank + 1)


def _weighted_rrf(
    dense_hits: list[dict],
    sparse_hits: list[dict],
    dense_weight: float = DEFAULT_DENSE_WEIGHT,
    sparse_weight: float = DEFAULT_SPARSE_WEIGHT,
    k: int = RRF_K,
) -> list[tuple[str, float]]:
    """Fuse two ranked result lists with weighted Reciprocal Rank Fusion.

    Each hit should be a dict with keys: ``id`` (unique str) and ``rank`` (int, 0-indexed).

    Returns:
        List of (doc_id, fused_score) sorted descending by fused_score.
    """
    fused: dict[str, float] = {}

    for hit in dense_hits:
        doc_id = hit["id"]
        fused[doc_id] = fused.get(doc_id, 0.0) + dense_weight * _rrf_score(hit["rank"], k)

    for hit in sparse_hits:
        doc_id = hit["id"]
        fused[doc_id] = fused.get(doc_id, 0.0) + sparse_weight * _rrf_score(hit["rank"], k)

    # Sort by fused score descending
    sorted_items = sorted(fused.items(), key=lambda x: x[1], reverse=True)
    return sorted_items


class HybridRetriever:
    """Retriever that runs dense (ChromaDB) and sparse (BM25) search,
    then fuses results with weighted RRF.

    The BM25 index is lazily built from the ChromaDB collection on first use,
    and can be rebuilt after ingestion via :meth:`rebuild_bm25`.
    """

    def __init__(
        self,
        collection_name: str,
        dense_weight: float = DEFAULT_DENSE_WEIGHT,
        sparse_weight: float = DEFAULT_SPARSE_WEIGHT,
        rrf_k: int = RRF_K,
    ):
        self.collection_name = collection_name
        self.dense_weight = dense_weight
        self.sparse_weight = sparse_weight
        self.rrf_k = rrf_k
        self._embedder = get_embedder()
        self._bm25: BM25Index | None = None
        self._bm25_doc_ids: list[str] = []  # ChromaDB IDs parallel to BM25 corpus

    # ── BM25 lifecycle ──────────────────────────────────────────────

    def _ensure_bm25(self):
        """Build the BM25 index from ChromaDB if not already built."""
        if self._bm25 is not None:
            return

        collection = get_or_create_collection(self.collection_name)
        # Fetch all documents (for MVP-scale collections this is fine; a
        # production system would use an inverted-index backend).
        result = collection.get()
        documents = result.get("documents") or []
        ids = result.get("ids") or []

        if not documents:
            logger.warning(
                "BM25: collection '%s' is empty — sparse retrieval disabled",
                self.collection_name,
            )
            self._bm25 = BM25Index([])
            self._bm25_doc_ids = []
            return

        self._bm25 = BM25Index(documents)
        self._bm25_doc_ids = list(ids)
        logger.info(
            "BM25 index built for '%s': %d documents",
            self.collection_name,
            len(documents),
        )

    def rebuild_bm25(self):
        """Force-rebuild the BM25 index (call after ingestion)."""
        self._bm25 = None
        self._bm25_doc_ids = []
        self._ensure_bm25()

    # ── Dense retrieval (ChromaDB) ──────────────────────────────────

    def _dense_retrieve(
        self, query: str, k: int, filter_metadata: dict | None
    ) -> list[dict]:
        """Run dense (embedding) retrieval.

        Returns:
            List of hits: {id, rank, distance, document, metadata}
        """
        collection = get_or_create_collection(self.collection_name)

        query_embedding = self._embedder.embed_query(query)
        where = filter_metadata if filter_metadata else None

        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        hits: list[dict] = []
        if results.get("ids") and results["ids"][0]:
            for rank, doc_id in enumerate(results["ids"][0]):
                hits.append({
                    "id": doc_id,
                    "rank": rank,
                    "distance": (
                        results["distances"][0][rank]
                        if results.get("distances") and results["distances"][0]
                        else 0.0
                    ),
                    "document": (
                        results["documents"][0][rank]
                        if results.get("documents") and results["documents"][0]
                        else ""
                    ),
                    "metadata": (
                        results["metadatas"][0][rank]
                        if results.get("metadatas") and results["metadatas"][0]
                        else {}
                    ),
                })
        return hits

    # ── Sparse retrieval (BM25) ─────────────────────────────────────

    def _sparse_retrieve(self, query: str, k: int) -> list[dict]:
        """Run sparse (BM25) retrieval.

        Returns:
            List of hits: {id, rank, score, document}
        """
        self._ensure_bm25()
        if self._bm25 is None or self._bm25.doc_count == 0:
            return []

        scored = self._bm25.search(query, k=k)

        hits: list[dict] = []
        for rank, (doc_idx, score) in enumerate(scored):
            doc_id = self._bm25_doc_ids[doc_idx] if doc_idx < len(self._bm25_doc_ids) else f"bm25_{doc_idx}"
            document = self._bm25.get_document(doc_idx)
            hits.append({
                "id": doc_id,
                "rank": rank,
                "score": score,
                "document": document,
            })
        return hits

    # ── Public API ──────────────────────────────────────────────────

    def retrieve(
        self,
        query: str,
        k: int = 5,
        filter_metadata: dict | None = None,
        dense_k: int | None = None,
        sparse_k: int | None = None,
    ) -> list[Document]:
        """Hybrid retrieval: dense + BM25 → weighted RRF fusion.

        Args:
            query: Search query text.
            k: Number of final results to return.
            filter_metadata: Optional ChromaDB ``where`` clause (dense only).
            dense_k: How many dense candidates to fetch (default k*2).
            sparse_k: How many BM25 candidates to fetch (default k*2).

        Returns:
            List of LangChain Document objects, sorted by RRF score.
        """
        if not query or not query.strip():
            return []

        dk = dense_k or max(k * 2, 10)
        sk = sparse_k or max(k * 2, 10)

        # Run both retrievals
        dense_hits = self._dense_retrieve(query, dk, filter_metadata)
        sparse_hits = self._sparse_retrieve(query, sk)

        logger.debug(
            "Hybrid retrieve: dense=%d hits, sparse=%d hits for '%s'",
            len(dense_hits), len(sparse_hits), query[:80],
        )

        # Fuse with weighted RRF
        fused = _weighted_rrf(
            dense_hits,
            sparse_hits,
            dense_weight=self.dense_weight,
            sparse_weight=self.sparse_weight,
            k=self.rrf_k,
        )

        # Build a lookup: doc_id → {dense hit / sparse hit}
        dense_lookup: dict[str, dict] = {h["id"]: h for h in dense_hits}
        sparse_lookup: dict[str, dict] = {h["id"]: h for h in sparse_hits}

        documents: list[Document] = []
        for doc_id, rrf_score in fused[:k]:
            # Prefer dense metadata when available (richer)
            dh = dense_lookup.get(doc_id)
            sh = sparse_lookup.get(doc_id)
            source_hit = dh or sh

            if source_hit is None:
                continue

            metadata: dict[str, Any] = source_hit.get("metadata", {}).copy() if dh else {}
            metadata["rrf_score"] = round(rrf_score, 6)
            metadata["collection"] = self.collection_name
            if dh:
                metadata["dense_rank"] = dh["rank"]
                metadata["dense_distance"] = dh.get("distance", 0.0)
            if sh:
                metadata["sparse_rank"] = sh["rank"]
                metadata["bm25_score"] = round(sh.get("score", 0.0), 4)
            metadata["source"] = "hybrid"

            documents.append(
                Document(
                    page_content=source_hit.get("document", ""),
                    metadata=metadata,
                )
            )

        return documents

    def retrieve_for_context(
        self, query: str, k: int = 5, filter_metadata: dict | None = None
    ) -> str:
        """Retrieve and format results as a context string for LLM prompts."""
        docs = self.retrieve(query, k, filter_metadata)
        if not docs:
            return ""

        parts: list[str] = []
        for i, doc in enumerate(docs, 1):
            parts.append(f"--- 参考资料 {i} ---\n{doc.page_content}")

        return "\n\n".join(parts)

    @property
    def bm25_ready(self) -> bool:
        """Whether the BM25 index is built and non-empty."""
        self._ensure_bm25()
        return self._bm25 is not None and self._bm25.doc_count > 0


# ── Named retrievers (lazy singletons) ──────────────────────────────

_retrievers: dict[str, HybridRetriever] = {}


def _get_hybrid_retriever(collection_name: str) -> HybridRetriever:
    """Get or create a HybridRetriever for *collection_name*."""
    if collection_name not in _retrievers:
        _retrievers[collection_name] = HybridRetriever(collection_name)
    return _retrievers[collection_name]


def get_question_retriever() -> HybridRetriever:
    return _get_hybrid_retriever("question_bank")


def get_knowledge_retriever() -> HybridRetriever:
    return _get_hybrid_retriever("knowledge_base")


def get_resume_retriever() -> HybridRetriever:
    return _get_hybrid_retriever("resume_chunks")


def rebuild_all_bm25():
    """Rebuild BM25 indexes for all cached retrievers.

    Call this after bulk ingestion to refresh sparse indexes.
    """
    for name, retriever in _retrievers.items():
        logger.info("Rebuilding BM25 for '%s'", name)
        retriever.rebuild_bm25()
