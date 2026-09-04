"""Unit tests for HttpAgentClient. No real Person C service required —
all HTTP interaction is mocked via httpx.MockTransport, mirroring
tests/unit/test_llm_ollama_provider.py and test_rag_embeddings.py."""

import httpx
import pytest

from app.clients.agent_client import HttpAgentClient
from app.core.exceptions import ServiceUnavailableError, UpstreamServiceError
from app.schemas.agent import AgentRunRequest


def make_client(handler) -> HttpAgentClient:
    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    return HttpAgentClient(base_url="http://localhost:8100", timeout_seconds=5.0, client=client)


def make_request(**overrides) -> AgentRunRequest:
    defaults = dict(
        run_id="run-1",
        request_id="req-1",
        user_id="user-1",
        role="engineer",
        task="summarize the latest incident report",
    )
    defaults.update(overrides)
    return AgentRunRequest(**defaults)


@pytest.mark.anyio
async def test_run_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/agent/run"
        return httpx.Response(
            200,
            json={
                "run_id": "run-1",
                "status": "completed",
                "answer": "Here is the summary.",
                "plan_summary": ["searched documents", "summarized findings"],
                "tools_used": ["document_search"],
                "sources": [],
            },
        )

    client = make_client(handler)
    result = await client.run(make_request())

    assert result.status == "completed"
    assert result.answer == "Here is the summary."
    assert result.tools_used == ["document_search"]


@pytest.mark.anyio
async def test_run_failed_status_from_agent() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"run_id": "run-1", "status": "failed", "error_message": "could not complete"}
        )

    client = make_client(handler)
    result = await client.run(make_request())

    assert result.status == "failed"
    assert result.error_message == "could not complete"


@pytest.mark.anyio
async def test_run_connection_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    client = make_client(handler)
    with pytest.raises(ServiceUnavailableError):
        await client.run(make_request())


@pytest.mark.anyio
async def test_run_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out", request=request)

    client = make_client(handler)
    with pytest.raises(ServiceUnavailableError):
        await client.run(make_request())


@pytest.mark.anyio
async def test_run_non_200_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="internal error")

    client = make_client(handler)
    with pytest.raises(UpstreamServiceError):
        await client.run(make_request())


@pytest.mark.anyio
async def test_run_malformed_json_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not json at all")

    client = make_client(handler)
    with pytest.raises(UpstreamServiceError):
        await client.run(make_request())


@pytest.mark.anyio
async def test_run_response_fails_contract_validation() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": "shape"})

    client = make_client(handler)
    with pytest.raises(UpstreamServiceError):
        await client.run(make_request())


@pytest.mark.anyio
async def test_run_response_with_invalid_status_literal() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"run_id": "run-1", "status": "in_progress"})

    client = make_client(handler)
    with pytest.raises(UpstreamServiceError):
        await client.run(make_request())


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_run_sends_context_and_internal_token() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json
        captured["json"] = json.loads(request.content)
        captured["token"] = request.headers.get("x-internal-service-token")
        return httpx.Response(200, json={"run_id": "run-1", "status": "completed"})

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    agent_client = HttpAgentClient(
        base_url="http://localhost:8100",
        timeout_seconds=120.0,
        internal_service_token="secret",
        client=client,
    )
    await agent_client.run(make_request(context={"unit": "unit-a"}))
    await client.aclose()

    assert captured["token"] == "secret"
    assert captured["json"]["context"] == {"unit": "unit-a"}


@pytest.mark.anyio
async def test_run_uses_configured_120_second_timeout() -> None:
    from app.core.config import settings

    assert settings.agent_service_timeout_seconds == 120.0
