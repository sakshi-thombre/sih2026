"""Unit tests for OllamaProvider. No real Ollama instance required —
all HTTP interaction is mocked via httpx.MockTransport."""

import httpx
import pytest
from pydantic import BaseModel

from app.core.exceptions import ServiceUnavailableError, UpstreamServiceError
from app.llm.ollama import OllamaProvider


def make_provider(handler) -> OllamaProvider:
    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    return OllamaProvider(
        base_url="http://localhost:11434",
        model="qwen3:8b",
        timeout_seconds=5.0,
        client=client,
    )


def test_provider_configuration() -> None:
    provider = OllamaProvider(base_url="http://localhost:11434/", model="qwen3:8b", timeout_seconds=10.0)
    assert provider.model_name == "qwen3:8b"
    assert provider._base_url == "http://localhost:11434"  # trailing slash stripped


@pytest.mark.anyio
async def test_generate_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/generate"
        return httpx.Response(200, json={"response": "A pressure relief valve protects equipment."})

    provider = make_provider(handler)
    text = await provider.generate("Explain a pressure relief valve.")
    assert text == "A pressure relief valve protects equipment."


@pytest.mark.anyio
async def test_generate_connection_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    provider = make_provider(handler)
    with pytest.raises(ServiceUnavailableError):
        await provider.generate("hello")


@pytest.mark.anyio
async def test_generate_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out", request=request)

    provider = make_provider(handler)
    with pytest.raises(ServiceUnavailableError):
        await provider.generate("hello")


@pytest.mark.anyio
async def test_generate_non_200_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="internal error")

    provider = make_provider(handler)
    with pytest.raises(UpstreamServiceError):
        await provider.generate("hello")


@pytest.mark.anyio
async def test_generate_malformed_json_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not json at all")

    provider = make_provider(handler)
    with pytest.raises(UpstreamServiceError):
        await provider.generate("hello")


@pytest.mark.anyio
async def test_generate_missing_response_field() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": "shape"})

    provider = make_provider(handler)
    with pytest.raises(UpstreamServiceError):
        await provider.generate("hello")


class _Checklist(BaseModel):
    title: str
    items: list[str]


@pytest.mark.anyio
async def test_generate_structured_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = {"title": "Pre-startup checklist", "items": ["Check valves", "Check pressure"]}
        import json

        return httpx.Response(200, json={"response": json.dumps(payload)})

    provider = make_provider(handler)
    result = await provider.generate_structured("Generate a checklist", _Checklist)
    assert isinstance(result, _Checklist)
    assert result.title == "Pre-startup checklist"


@pytest.mark.anyio
async def test_generate_structured_invalid_schema_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"response": '{"unexpected": "data"}'})

    provider = make_provider(handler)
    with pytest.raises(UpstreamServiceError):
        await provider.generate_structured("Generate a checklist", _Checklist)


@pytest.mark.anyio
async def test_embed_not_implemented() -> None:
    provider = OllamaProvider(base_url="http://localhost:11434", model="qwen3:8b")
    with pytest.raises(NotImplementedError):
        await provider.embed("some text")


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
