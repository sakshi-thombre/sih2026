"""Unit tests for VectorStoreRetriever. Uses fake embedding provider and
vector store — no network, no real Ollama."""

from typing import Any

import pytest

from app.rag.base import DocumentChunk
from app.rag.embeddings import EmbeddingProvider
from app.rag.retriever import VectorStoreRetriever
from app.rag.vector_store import VectorStore


class FakeEmbeddingProvider(EmbeddingProvider):
    def __init__(self, vector: list[float] | None = None) -> None:
        self._vector = vector or [1.0, 0.0]

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vector for _ in texts]


class FakeVectorStore(VectorStore):
    def __init__(self, results: list[DocumentChunk] | None = None) -> None:
        self._results = results or []
        self.last_query_embedding: list[float] | None = None
        self.last_top_k: int | None = None

    def add(self, chunks: Any, embeddings: Any) -> None:
        raise NotImplementedError

    def search(self, query_embedding: list[float], top_k: int) -> list[DocumentChunk]:
        self.last_query_embedding = query_embedding
        self.last_top_k = top_k
        return self._results[:top_k]

    def delete(self, document_id: str) -> None:
        raise NotImplementedError

    def clear(self) -> None:
        raise NotImplementedError


def make_result(chunk_id: str, score: float) -> DocumentChunk:
    return DocumentChunk(
        document_id="doc-1",
        filename="sop.pdf",
        chunk_id=chunk_id,
        text="relevant text",
        score=score,
        page_number=1,
        chunk_index=0,
    )


@pytest.mark.anyio
async def test_retrieve_returns_ranked_results() -> None:
    results = [make_result("chunk-1", 0.9), make_result("chunk-2", 0.5)]
    retriever = VectorStoreRetriever(FakeVectorStore(results), FakeEmbeddingProvider())

    output = await retriever.retrieve("what safety incidents occurred", top_k=5)

    assert output == results


@pytest.mark.anyio
async def test_retrieve_passes_top_k_through() -> None:
    store = FakeVectorStore([make_result("chunk-1", 0.9)])
    retriever = VectorStoreRetriever(store, FakeEmbeddingProvider())

    await retriever.retrieve("query", top_k=3)

    assert store.last_top_k == 3


@pytest.mark.anyio
async def test_retrieve_with_no_results_returns_empty_list() -> None:
    retriever = VectorStoreRetriever(FakeVectorStore([]), FakeEmbeddingProvider())

    output = await retriever.retrieve("query", top_k=5)

    assert output == []


@pytest.mark.anyio
async def test_retrieve_rejects_empty_query() -> None:
    retriever = VectorStoreRetriever(FakeVectorStore([]), FakeEmbeddingProvider())

    with pytest.raises(ValueError):
        await retriever.retrieve("   ", top_k=5)


@pytest.mark.anyio
async def test_retrieve_rejects_invalid_top_k() -> None:
    retriever = VectorStoreRetriever(FakeVectorStore([]), FakeEmbeddingProvider())

    with pytest.raises(ValueError):
        await retriever.retrieve("query", top_k=0)


@pytest.mark.anyio
async def test_retrieve_results_carry_citation_metadata() -> None:
    results = [make_result("chunk-1", 0.9)]
    retriever = VectorStoreRetriever(FakeVectorStore(results), FakeEmbeddingProvider())

    output = await retriever.retrieve("query", top_k=1)

    assert output[0].document_id == "doc-1"
    assert output[0].filename == "sop.pdf"
    assert output[0].page_number == 1


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
