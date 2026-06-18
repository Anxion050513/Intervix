"""ChromaDB vector store client management."""
import chromadb
from chromadb.config import Settings as ChromaSettings

from server.config import settings

# Lazy-initialized clients
_client: chromadb.PersistentClient | None = None


def get_chroma_client() -> chromadb.PersistentClient:
    """Get or create the ChromaDB persistent client."""
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(
            path=settings.chroma_persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
    return _client


COLLECTION_NAMES = {
    "question_bank": "面试题库",
    "knowledge_base": "知识库",
    "resume_chunks": "简历分块",
}


def get_or_create_collection(name: str):
    """Get or create a named ChromaDB collection."""
    client = get_chroma_client()
    return client.get_or_create_collection(
        name=name,
        metadata={"description": COLLECTION_NAMES.get(name, "")},
    )
