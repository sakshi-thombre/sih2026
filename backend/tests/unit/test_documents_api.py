"""API-level tests for POST /api/v1/documents/upload and /search.

Uses fake in-memory EmbeddingProvider/VectorStore injected via FastAPI
dependency overrides, mirroring tests/unit/test_llm_api.py — no HTTP
to Ollama, no real vector store I/O.
"""

from typing import Any

from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_embedding_provider, get_settings, get_vector_store
from app.core.config import Settings, settings as real_settings
from app.core.exceptions import ServiceUnavailableError
from app.rag.base import DocumentChunk
from app.rag.embeddings import EmbeddingProvider
from app.rag.vector_store import VectorStore
from app.main import app


class FakeEmbeddingProvider(EmbeddingProvider):
    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]


class FailingEmbeddingProvider(EmbeddingProvider):
    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise ServiceUnavailableError("Local embedding service is unreachable")


class FakeVectorStore(VectorStore):
    def __init__(self, search_results: list[DocumentChunk] | None = None) -> None:
        self.added: list[tuple[Any, Any]] = []
        self._search_results = search_results or []

    def add(self, chunks: Any, embeddings: Any) -> None:
        self.added.append((chunks, embeddings))

    def search(self, query_embedding: list[float], top_k: int) -> list[DocumentChunk]:
        return self._search_results[:top_k]

    def delete(self, document_id: str) -> None:
        pass

    def clear(self) -> None:
        pass


client = TestClient(app)


def teardown_function() -> None:
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_embedding_provider, None)
    app.dependency_overrides.pop(get_vector_store, None)
    app.dependency_overrides.pop(get_settings, None)


def _override(embedding_provider: EmbeddingProvider, vector_store: VectorStore) -> None:
    """Overrides for an authenticated caller — the common case, used by
    every test below except the dedicated unauthenticated-request tests."""
    app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1", "role": "engineer"}
    app.dependency_overrides[get_embedding_provider] = lambda: embedding_provider
    app.dependency_overrides[get_vector_store] = lambda: vector_store


def _override_without_auth(embedding_provider: EmbeddingProvider, vector_store: VectorStore) -> None:
    """Same as `_override`, but get_current_user is intentionally NOT
    overridden — with no Authorization header, its get_bearer_token
    dependency raises UnauthorizedError before any Supabase call is
    attempted, mirroring test_agent_api.py::test_create_run_without_auth_fails_closed."""
    app.dependency_overrides[get_embedding_provider] = lambda: embedding_provider
    app.dependency_overrides[get_vector_store] = lambda: vector_store


def test_upload_success() -> None:
    vector_store = FakeVectorStore()
    _override(FakeEmbeddingProvider(), vector_store)

    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("sop.txt", b"Pressure relief valves protect equipment.", "text/plain")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["document"]["filename"] == "sop.txt"
    assert body["document"]["file_type"] == "txt"
    assert body["document"]["chunk_count"] == 1
    assert len(vector_store.added) == 1


def test_upload_rejects_unsupported_file_type() -> None:
    _override(FakeEmbeddingProvider(), FakeVectorStore())

    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("data.csv", b"a,b,c", "text/csv")},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_document"


def test_upload_rejects_empty_file() -> None:
    _override(FakeEmbeddingProvider(), FakeVectorStore())

    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("empty.txt", b"", "text/plain")},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_document"


def test_upload_rejects_oversized_file() -> None:
    _override(FakeEmbeddingProvider(), FakeVectorStore())
    app.dependency_overrides[get_settings] = lambda: Settings(max_upload_size_bytes=10)

    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("big.txt", b"this file is definitely larger than ten bytes", "text/plain")},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_document"


def test_upload_embedding_service_failure_returns_503() -> None:
    _override(FailingEmbeddingProvider(), FakeVectorStore())

    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("sop.txt", b"some safety content", "text/plain")},
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "service_unavailable"


def test_search_success() -> None:
    result = DocumentChunk(
        document_id="doc-1",
        filename="safety_report.pdf",
        chunk_id="doc-1:0",
        text="Unit 3 experienced a minor pressure excursion.",
        score=0.92,
        page_number=14,
        chunk_index=0,
    )
    _override(FakeEmbeddingProvider(), FakeVectorStore([result]))

    response = client.post(
        "/api/v1/documents/search",
        json={"query": "What safety incidents occurred in Unit 3?", "top_k": 5},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["query"] == "What safety incidents occurred in Unit 3?"
    assert len(body["results"]) == 1
    assert body["results"][0]["filename"] == "safety_report.pdf"
    assert body["results"][0]["page_number"] == 14
    assert body["results"][0]["score"] == 0.92


def test_search_with_no_results_returns_empty_list() -> None:
    _override(FakeEmbeddingProvider(), FakeVectorStore([]))

    response = client.post(
        "/api/v1/documents/search",
        json={"query": "anything", "top_k": 5},
    )

    assert response.status_code == 200
    assert response.json()["results"] == []


def test_search_rejects_empty_query() -> None:
    _override(FakeEmbeddingProvider(), FakeVectorStore())

    response = client.post("/api/v1/documents/search", json={"query": "", "top_k": 5})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_search_rejects_missing_query() -> None:
    _override(FakeEmbeddingProvider(), FakeVectorStore())

    response = client.post("/api/v1/documents/search", json={"top_k": 5})

    assert response.status_code == 422


def test_search_rejects_top_k_below_minimum() -> None:
    _override(FakeEmbeddingProvider(), FakeVectorStore())

    response = client.post("/api/v1/documents/search", json={"query": "test", "top_k": 0})

    assert response.status_code == 422


def test_search_rejects_top_k_above_maximum() -> None:
    _override(FakeEmbeddingProvider(), FakeVectorStore())

    response = client.post(
        "/api/v1/documents/search",
        json={"query": "test", "top_k": real_settings.max_top_k + 1},
    )

    assert response.status_code == 422


def test_upload_without_auth_returns_401() -> None:
    _override_without_auth(FakeEmbeddingProvider(), FakeVectorStore())

    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("sop.txt", b"Pressure relief valves protect equipment.", "text/plain")},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_search_without_auth_returns_401() -> None:
    _override_without_auth(FakeEmbeddingProvider(), FakeVectorStore())

    response = client.post(
        "/api/v1/documents/search",
        json={"query": "test", "top_k": 5},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_search_vector_store_unavailable_returns_503() -> None:
    class BrokenVectorStore(FakeVectorStore):
        def search(self, query_embedding: list[float], top_k: int) -> list[DocumentChunk]:
            raise ConnectionError("disk unavailable")

    _override(FakeEmbeddingProvider(), BrokenVectorStore())

    response = client.post("/api/v1/documents/search", json={"query": "test", "top_k": 5})

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "service_unavailable"
