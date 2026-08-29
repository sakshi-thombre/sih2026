"""Semantic retrieval, implementing the `Retriever` contract from
app/rag/base.py so the future agent layer can depend on that interface
regardless of which embedding provider or vector store backs it."""

from app.rag.base import DocumentChunk, Retriever
from app.rag.embeddings import EmbeddingProvider
from app.rag.vector_store import VectorStore


class VectorStoreRetriever(Retriever):
    def __init__(self, vector_store: VectorStore, embedding_provider: EmbeddingProvider) -> None:
        self._vector_store = vector_store
        self._embedding_provider = embedding_provider

    async def retrieve(self, query: str, top_k: int = 5) -> list[DocumentChunk]:
        if not query or not query.strip():
            raise ValueError("query must not be empty")
        if top_k <= 0:
            raise ValueError("top_k must be positive")

        embeddings = await self._embedding_provider.embed([query])
        query_embedding = embeddings[0]
        return self._vector_store.search(query_embedding, top_k)
