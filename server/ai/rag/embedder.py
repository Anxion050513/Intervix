"""Embedding model wrapper.

Supports:
- Alibaba DashScope (百炼) — free tier, native API
- Local HuggingFace model — offline fallback
"""
from typing import List
import httpx
from langchain_huggingface import HuggingFaceEmbeddings

from server.config import settings


class DashScopeEmbeddings:
    """Custom embedding wrapper for Alibaba DashScope (百炼) native API.

    Uses the native DashScope embedding endpoint instead of the
    incompatible 'compatible-mode' OpenAI proxy.
    """

    def __init__(self, api_key: str, model: str = "text-embedding-v2"):
        self.api_key = api_key
        self.model = model
        self.api_url = "https://dashscope.aliyuncs.com/api/v1/services/embeddings/text-embedding/text-embedding"
        self._client = httpx.Client(timeout=30)

    def embed_query(self, text: str) -> List[float]:
        return self.embed_documents([text])[0]

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        embeddings = []
        for text in texts:
            resp = self._client.post(
                self.api_url,
                json={
                    "model": self.model,
                    "input": {"texts": [text]},
                    "parameters": {"text_type": "query"},
                },
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            data = resp.json()
            if "output" not in data or "embeddings" not in data["output"]:
                raise RuntimeError(f"DashScope error: {data}")
            emb = data["output"]["embeddings"][0]["embedding"]
            embeddings.append(emb)
        return embeddings


def get_embedder():
    """Get the configured embedding model.

    Uses DashScope API if EMBEDDING_API_KEY is set.
    Falls back to local HuggingFace model.
    """
    if settings.embedding_api_key and settings.embedding_api_key != "none":
        return DashScopeEmbeddings(
            api_key=settings.embedding_api_key,
            model=settings.embedding_model,
        )

    # Local fallback
    return HuggingFaceEmbeddings(
        model_name="BAAI/bge-small-zh-v1.5",
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )
