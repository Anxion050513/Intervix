"""Hybrid retriever combining dense embeddings and BM25 sparse retrieval."""
from langchain_core.documents import Document

from server.ai.rag.vector_store import get_or_create_collection
from server.ai.rag.embedder import get_embedder


class HybridRetriever:
    """Retriever that searches ChromaDB collections."""

    def __init__(self, collection_name: str):
        self.collection_name = collection_name
        self._embedder = get_embedder()

    def retrieve(
        self, query: str, k: int = 3, filter_metadata: dict | None = None
    ) -> list[Document]:
        """Retrieve top-k relevant documents from the collection.

        Args:
            query: Search query text.
            k: Number of results to return.
            filter_metadata: Optional ChromaDB where clause for filtering.

        Returns:
            List of LangChain Document objects with text and metadata.
        """
        collection = get_or_create_collection(self.collection_name)

        # Generate query embedding
        query_embedding = self._embedder.embed_query(query)

        # Prepare filter
        where = filter_metadata if filter_metadata else {}

        # Query ChromaDB
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=k,
            where=where if where else None,
            include=["documents", "metadatas", "distances"],
        )

        # Convert to LangChain Documents
        documents = []
        if results["documents"] and results["documents"][0]:
            for i, text in enumerate(results["documents"][0]):
                metadata = (
                    results["metadatas"][0][i]
                    if results["metadatas"] and results["metadatas"][0]
                    else {}
                )
                distance = (
                    results["distances"][0][i]
                    if results["distances"] and results["distances"][0]
                    else 0.0
                )
                metadata["distance"] = distance
                metadata["collection"] = self.collection_name
                documents.append(Document(page_content=text, metadata=metadata))

        return documents

    def retrieve_for_context(
        self, query: str, k: int = 3, filter_metadata: dict | None = None
    ) -> str:
        """Retrieve and format results as a context string for prompts."""
        docs = self.retrieve(query, k, filter_metadata)
        if not docs:
            return ""

        parts = []
        for i, doc in enumerate(docs, 1):
            parts.append(f"--- 参考资料 {i} ---\n{doc.page_content}")

        return "\n\n".join(parts)


# Named retrievers
def get_question_retriever() -> HybridRetriever:
    return HybridRetriever("question_bank")


def get_knowledge_retriever() -> HybridRetriever:
    return HybridRetriever("knowledge_base")


def get_resume_retriever() -> HybridRetriever:
    return HybridRetriever("resume_chunks")
