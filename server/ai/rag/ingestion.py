"""Data ingestion into ChromaDB collections.

After every ingestion the corresponding BM25 index is automatically rebuilt
so hybrid retrievers always see fresh data.
"""
import logging
import uuid

from langchain_text_splitters import RecursiveCharacterTextSplitter

from server.ai.rag.vector_store import get_or_create_collection
from server.ai.rag.embedder import get_embedder

logger = logging.getLogger(__name__)


def ingest_documents(
    collection_name: str,
    texts: list[str],
    metadatas: list[dict] | None = None,
    ids: list[str] | None = None,
) -> int:
    """Ingest a batch of text documents into a ChromaDB collection.

    Args:
        collection_name: Target collection name.
        texts: List of document texts.
        metadatas: Optional list of metadata dicts (same length as texts).
        ids: Optional list of document IDs.

    Returns:
        Number of documents ingested.
    """
    collection = get_or_create_collection(collection_name)
    embedder = get_embedder()

    if ids is None:
        ids = [str(uuid.uuid4()) for _ in texts]
    if metadatas is None:
        metadatas = [{} for _ in texts]

    # Generate embeddings in batch
    embeddings = embedder.embed_documents(texts)

    collection.add(
        ids=ids,
        documents=texts,
        metadatas=metadatas,
        embeddings=embeddings,
    )

    # Rebuild BM25 for this collection so hybrid retrievers see new data
    _rebuild_bm25_for(collection_name)

    return len(texts)


def ingest_resume_chunks(
    resume_id: str, resume_text: str, chunk_size: int = 500, overlap: int = 50
) -> int:
    """Chunk and ingest a resume into the resume_chunks collection.

    Args:
        resume_id: Resume ID for metadata tracking.
        resume_text: Full resume text content.
        chunk_size: Max characters per chunk.
        overlap: Overlap between chunks.

    Returns:
        Number of chunks ingested.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=overlap,
        separators=["\n\n", "\n", "。", ".", " ", ""],
    )

    chunks = splitter.split_text(resume_text)
    if not chunks:
        return 0

    metadatas = [
        {"resume_id": resume_id, "chunk_index": i, "source": "resume"}
        for i in range(len(chunks))
    ]
    ids = [f"{resume_id}_chunk_{i}" for i in range(len(chunks))]

    count = ingest_documents("resume_chunks", chunks, metadatas, ids)

    # Rebuild BM25 so hybrid retrievers pick up the new data
    _rebuild_bm25_for("resume_chunks")

    return count


def ingest_questions(
    questions: list[dict], clear_existing: bool = False
) -> int:
    """Ingest interview questions into the question_bank collection.

    Args:
        questions: List of question dicts with keys:
            - question: question text
            - type: question type
            - difficulty: easy/medium/hard
            - topics: list of topic strings
            - reference_answer: optional reference answer
        clear_existing: If True, delete existing collection first.

    Returns:
        Number of questions ingested.
    """
    if clear_existing:
        try:
            from server.ai.rag.vector_store import get_chroma_client
            client = get_chroma_client()
            client.delete_collection("question_bank")
        except Exception:
            pass

    texts = []
    metadatas = []
    ids = []

    for q in questions:
        # Build searchable text
        text_parts = [
            f"问题：{q['question']}",
            f"类型：{q.get('type', 'technical')}",
            f"难度：{q.get('difficulty', 'medium')}",
        ]
        if q.get("topics"):
            text_parts.append(f"主题：{', '.join(q['topics'])}")

        texts.append("\n".join(text_parts))
        metadatas.append({
            "type": q.get("type", "technical"),
            "difficulty": q.get("difficulty", "medium"),
            "topics": ",".join(q.get("topics", [])),
            "reference_answer": q.get("reference_answer", ""),
        })
        ids.append(str(uuid.uuid4()))

    count = ingest_documents("question_bank", texts, metadatas, ids)
    # BM25 is already rebuilt inside ingest_documents()
    return count


def _rebuild_bm25_for(collection_name: str):
    """Rebuild the BM25 index for *collection_name* if it is already cached."""
    try:
        from server.ai.rag.retriever import _retrievers

        retriever = _retrievers.get(collection_name)
        if retriever is not None:
            retriever.rebuild_bm25()
            logger.info("BM25 rebuilt for '%s' after ingestion", collection_name)
    except Exception:
        logger.debug("BM25 rebuild skipped for '%s' (retriever not yet initialized)", collection_name)
