import json

import httpx
import pytest

from app.agent import Agent
from app.backend_client import BackendToolClient
from app.schemas import AgentPlan, AgentStep


@pytest.mark.asyncio
async def test_backend_tool_client_sends_contract_and_token() -> None:
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["json"] = json.loads(request.content)
        return httpx.Response(200, json={"success": True, "data": [{"id": "doc-1"}], "error": None})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    tool_client = BackendToolClient(
        base_url="http://backend:8000/",
        token="secret-token",
        client=client,
    )

    result = await tool_client.execute("run-1", "document_search", {"query": "Unit 3", "top_k": 5})
    await client.aclose()

    assert result["success"] is True
    assert captured["url"] == "http://backend:8000/api/v1/agent/tools/execute"
    assert captured["headers"]["x-internal-service-token"] == "secret-token"
    assert captured["json"] == {
        "run_id": "run-1",
        "tool_name": "document_search",
        "input": {"query": "Unit 3", "top_k": 5},
    }


@pytest.mark.asyncio
async def test_backend_tool_client_rejects_non_2xx() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"detail": "forbidden"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    tool_client = BackendToolClient(base_url="http://backend:8000", token="secret", client=client)

    from app.backend_client import BackendToolError
    with pytest.raises(BackendToolError, match="HTTP 403"):
        await tool_client.execute("run-1", "document_search", {"query": "Unit 3"})

    await client.aclose()


@pytest.mark.asyncio
async def test_agent_execute_plan_reaches_backend_client() -> None:
    calls = []

    class FakeBackend:
        async def execute(self, run_id: str, tool_name: str, input_data: dict) -> dict:
            calls.append((run_id, tool_name, input_data))
            return {"success": True, "data": [{"document_id": "doc-1"}]}

    agent = Agent(backend_client=FakeBackend())
    plan = AgentPlan(
        steps=[AgentStep(step=1, tool="document_search", description="Find Unit 3 safety reports")]
    )

    result = await agent.execute_plan("run-123", plan)

    assert calls == [
        ("run-123", "document_search", {"query": "Find Unit 3 safety reports"})
    ]
    assert result[0]["result"] == [{"document_id": "doc-1"}]


@pytest.mark.asyncio
async def test_agent_context_is_included_in_planner_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    class FakeLLM:
        async def generate(self, prompt: str) -> str:
            captured["prompt"] = prompt
            return '{"steps": [{"step": 1, "tool": "document_search", "description": "Find relevant documents"}]}'

    agent = Agent(backend_client=object())
    agent.llm = FakeLLM()

    await agent.create_plan(
        "Find safety information",
        {"unit": "Unit 3", "requested_by": "engineer"},
    )

    assert '"unit": "Unit 3"' in captured["prompt"]
    assert '"requested_by": "engineer"' in captured["prompt"]


@pytest.mark.asyncio
async def test_backend_tool_client_rejects_invalid_backend_json() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not-json")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    tool_client = BackendToolClient(base_url="http://backend:8000", token="secret", client=client)

    from app.backend_client import BackendToolError
    with pytest.raises(BackendToolError, match="invalid response"):
        await tool_client.execute("run-1", "document_search", {"query": "Unit 3"})

    await client.aclose()


@pytest.mark.asyncio
async def test_backend_tool_client_can_omit_token_for_local_development() -> None:
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        return httpx.Response(200, json={"success": True, "data": [], "error": None})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    tool_client = BackendToolClient(base_url="http://backend:8000", token=None, client=client)

    await tool_client.execute("run-1", "document_search", {"query": "Unit 3"})
    await client.aclose()

    assert "x-internal-service-token" not in captured["headers"]


@pytest.mark.asyncio
async def test_backend_tool_client_wraps_timeout() -> None:
    from app.backend_client import BackendToolError

    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    tool_client = BackendToolClient(base_url="http://backend:8000", token="secret", client=client)

    with pytest.raises(BackendToolError, match="timed out"):
        await tool_client.execute("run-1", "document_search", {"query": "Unit 3"})
    await client.aclose()


@pytest.mark.asyncio
async def test_backend_tool_client_wraps_http_and_invalid_response() -> None:
    from app.backend_client import BackendToolError

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "boom"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    tool_client = BackendToolClient(base_url="http://backend:8000", token="secret", client=client)

    with pytest.raises(BackendToolError, match="HTTP 500"):
        await tool_client.execute("run-1", "document_search", {"query": "Unit 3"})
    await client.aclose()

    async def bad_json(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not-json")

    client = httpx.AsyncClient(transport=httpx.MockTransport(bad_json))
    tool_client = BackendToolClient(base_url="http://backend:8000", token="secret", client=client)

    with pytest.raises(BackendToolError, match="invalid response"):
        await tool_client.execute("run-1", "document_search", {"query": "Unit 3"})
    await client.aclose()
