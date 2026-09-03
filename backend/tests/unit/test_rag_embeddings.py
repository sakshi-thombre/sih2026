"""Unit tests for OllamaEmbeddingProvider. No real Ollama instance
required — all HTTP interaction is mocked via httpx.MockTransport,
mirroring tests/unit/test_llm_ollama_provider.py."""

import httpx
import pytest

from app.core.exceptions import ServiceUnavailableError, UpstreamServiceError
from app.rag.embeddings import OllamaEmbeddingProvider


def make_provider(handler, batch_size: int = 16) -> OllamaEmbeddingProvider:
    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    return OllamaEmbeddingProvider(
        base_url="http://localhost:11434",
        model="nomic-embed-text",
        timeout_seconds=5.0,
        batch_size=batch_size,
        client=client,
    )


@pytest.mark.anyio
async def test_embed_empty_list_returns_empty_without_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("should not make a request for an empty input")

    provider = make_provider(handler)
    result = await provider.embed([])
    assert result == []


@pytest.mark.anyio
async def test_embed_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/embed"
        payload = request.read()
        assert b"nomic-embed-text" in payload
        return httpx.Response(200, json={"embeddings": [[0.1, 0.2, 0.3]]})

    provider = make_provider(handler)
    result = await provider.embed(["a pressure relief valve"])
    assert result == [[0.1, 0.2, 0.3]]


@pytest.mark.anyio
async def test_embed_batches_requests() -> None:
    import json

    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        batch = json.loads(request.read())["input"]
        return httpx.Response(200, json={"embeddings": [[0.1] for _ in batch]})

    provider = make_provider(handler, batch_size=2)
    texts = ["a", "b", "c", "d", "e"]
    result = await provider.embed(texts)

    assert len(result) == 5
    assert call_count == 3  # batches of 2, 2, 1


@pytest.mark.anyio
async def test_embed_connection_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    provider = make_provider(handler)
    with pytest.raises(ServiceUnavailableError):
        await provider.embed(["text"])


@pytest.mark.anyio
async def test_embed_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out", request=request)

    provider = make_provider(handler)
    with pytest.raises(ServiceUnavailableError):
        await provider.embed(["text"])


@pytest.mark.anyio
async def test_embed_non_200_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="internal error")

    provider = make_provider(handler)
    with pytest.raises(UpstreamServiceError):
        await provider.embed(["text"])


@pytest.mark.anyio
async def test_embed_malformed_json_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not json at all")

    provider = make_provider(handler)
    with pytest.raises(UpstreamServiceError):
        await provider.embed(["text"])


@pytest.mark.anyio
async def test_embed_missing_embeddings_field() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": "shape"})

    provider = make_provider(handler)
    with pytest.raises(UpstreamServiceError):
        await provider.embed(["text"])


@pytest.mark.anyio
async def test_embed_wrong_vector_count() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"embeddings": [[0.1, 0.2]]})  # only 1, expected 2

    provider = make_provider(handler)
    with pytest.raises(UpstreamServiceError):
        await provider.embed(["text one", "text two"])


@pytest.mark.anyio
async def test_embed_malformed_vector_shape() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"embeddings": ["not-a-vector"]})

    provider = make_provider(handler)
    with pytest.raises(UpstreamServiceError):
        await provider.embed(["text"])


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
