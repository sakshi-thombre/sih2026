"""API-level tests for /api/v1/agent/*.

Uses fake in-memory RunStore/ActionStore/AgentClient injected via
FastAPI dependency overrides, mirroring tests/unit/test_llm_api.py and
test_documents_api.py — no real Person C service, no real Ollama.
"""

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.deps import (
    get_action_store,
    get_agent_client,
    get_current_user,
    get_run_store,
    get_service_action_store,
    get_service_run_store,
    get_tool_registry,
    verify_internal_service,
)
from app.clients.agent_client import AgentClient
from app.core.exceptions import ServiceUnavailableError
from app.main import app
from app.runs.store import InMemoryActionStore, InMemoryRunStore
from app.schemas.agent import AgentRunRequest, AgentRunResult
from app.tools.base import Tool, ToolRegistry, ToolResult
from pydantic import BaseModel


class EchoInput(BaseModel):
    message: str


class EchoTool(Tool):
    name = "echo"
    description = "echoes the input"
    input_schema = EchoInput
    required_role = None

    async def run(self, input_data: BaseModel) -> ToolResult:
        assert isinstance(input_data, EchoInput)
        return ToolResult(success=True, data={"echoed": input_data.message})


class FakeAgentClient(AgentClient):
    def __init__(self, result: AgentRunResult | None = None, error: Exception | None = None) -> None:
        self._result = result
        self._error = error

    async def run(self, request: AgentRunRequest) -> AgentRunResult:
        if self._error is not None:
            raise self._error
        assert self._result is not None
        return self._result.model_copy(update={"run_id": request.run_id})


def success_result() -> AgentRunResult:
    return AgentRunResult(
        run_id="placeholder",
        status="completed",
        answer="The final answer.",
        plan_summary=["searched documents"],
        tools_used=["document_search"],
        sources=[],
    )


client = TestClient(app)


def teardown_function() -> None:
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_run_store, None)
    app.dependency_overrides.pop(get_action_store, None)
    app.dependency_overrides.pop(get_service_run_store, None)
    app.dependency_overrides.pop(get_service_action_store, None)
    app.dependency_overrides.pop(get_agent_client, None)
    app.dependency_overrides.pop(get_tool_registry, None)
    app.dependency_overrides.pop(verify_internal_service, None)


def _override(agent_client: AgentClient, role: str = "engineer") -> tuple[InMemoryRunStore, InMemoryActionStore]:
    run_store = InMemoryRunStore()
    action_store = InMemoryActionStore()
    app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1", "role": role}
    app.dependency_overrides[get_run_store] = lambda: run_store
    app.dependency_overrides[get_action_store] = lambda: action_store
    # /tools/execute (called by Person C's service, not the frontend)
    # depends on the service-scoped stores instead — see
    # app.api.deps.get_service_run_store. Point them at the same fakes
    # so the two paths share state in tests, mirroring how in
    # production both are really just the same agent_action_logs table.
    app.dependency_overrides[get_service_run_store] = lambda: run_store
    app.dependency_overrides[get_service_action_store] = lambda: action_store
    app.dependency_overrides[get_agent_client] = lambda: agent_client
    registry = ToolRegistry()
    registry.register(EchoTool())
    app.dependency_overrides[get_tool_registry] = lambda: registry
    return run_store, action_store


def test_create_run_returns_202_and_queued_status() -> None:
    _override(FakeAgentClient(result=success_result()))

    response = client.post("/api/v1/agent/runs", json={"task": "summarize the incident log"})

    assert response.status_code == 202
    body = response.json()
    assert body["status"] in ("queued", "completed")  # background task may finish before response returns
    assert "run_id" in body


def test_create_run_rejects_empty_task() -> None:
    _override(FakeAgentClient(result=success_result()))

    response = client.post("/api/v1/agent/runs", json={"task": ""})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_create_run_without_auth_fails_closed() -> None:
    run_store = InMemoryRunStore()
    action_store = InMemoryActionStore()
    app.dependency_overrides[get_run_store] = lambda: run_store
    app.dependency_overrides[get_action_store] = lambda: action_store
    app.dependency_overrides[get_agent_client] = lambda: FakeAgentClient(result=success_result())
    # get_current_user intentionally NOT overridden — with no Authorization
    # header, its get_bearer_token dependency raises UnauthorizedError before
    # any Supabase call is attempted, and the app's exception handler turns
    # that into a clean 401 rather than creating a run.
    response = client.post("/api/v1/agent/runs", json={"task": "do something"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"
    assert run_store._runs == {}  # nothing was created


def test_get_run_after_successful_execution() -> None:
    _override(FakeAgentClient(result=success_result()))

    create_response = client.post("/api/v1/agent/runs", json={"task": "find safety incidents"})
    run_id = create_response.json()["run_id"]

    response = client.get(f"/api/v1/agent/runs/{run_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["answer"] == "The final answer."
    assert body["tools_used"] == ["document_search"]


def test_get_run_unknown_id_returns_404() -> None:
    _override(FakeAgentClient(result=success_result()))

    response = client.get("/api/v1/agent/runs/does-not-exist")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_get_run_status_endpoint() -> None:
    _override(FakeAgentClient(result=success_result()))

    create_response = client.post("/api/v1/agent/runs", json={"task": "t"})
    run_id = create_response.json()["run_id"]

    response = client.get(f"/api/v1/agent/runs/{run_id}/status")

    assert response.status_code == 200
    assert response.json()["run_id"] == run_id


def test_get_run_actions_endpoint() -> None:
    _override(FakeAgentClient(result=success_result()))

    create_response = client.post("/api/v1/agent/runs", json={"task": "t"})
    run_id = create_response.json()["run_id"]

    response = client.get(f"/api/v1/agent/runs/{run_id}/actions")

    assert response.status_code == 200
    body = response.json()
    event_types = [a["event_type"] for a in body["actions"]]
    assert "run_created" in event_types


def test_run_failure_surfaces_as_failed_status_not_http_error() -> None:
    """Agent service being unreachable happens in the background task,
    after the 202 response — the frontend discovers it by polling."""
    _override(FakeAgentClient(error=ServiceUnavailableError("Agent service is unreachable")))

    create_response = client.post("/api/v1/agent/runs", json={"task": "t"})
    assert create_response.status_code == 202
    run_id = create_response.json()["run_id"]

    response = client.get(f"/api/v1/agent/runs/{run_id}")
    assert response.json()["status"] == "failed"


@pytest.mark.anyio
async def test_cancel_queued_run() -> None:
    """Creates a run directly via task_service (bypassing the
    fire-and-forget background execution the POST /runs route
    triggers) so it's still QUEUED when cancelled, then cancels it
    through the real HTTP route."""
    run_store = InMemoryRunStore()
    action_store = InMemoryActionStore()
    app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1", "role": "engineer"}
    app.dependency_overrides[get_run_store] = lambda: run_store
    app.dependency_overrides[get_action_store] = lambda: action_store
    app.dependency_overrides[get_agent_client] = lambda: FakeAgentClient(result=success_result())

    from app.services import task_service

    run = await task_service.create_run(
        task="t", context={}, user_id="user-1", role="engineer",
        run_store=run_store, action_store=action_store,
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post(f"/api/v1/agent/runs/{run.run_id}/cancel")

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


def test_cancel_already_completed_run_returns_409() -> None:
    _override(FakeAgentClient(result=success_result()))

    create_response = client.post("/api/v1/agent/runs", json={"task": "t"})
    run_id = create_response.json()["run_id"]

    response = client.post(f"/api/v1/agent/runs/{run_id}/cancel")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_state"


def test_cancel_unknown_run_returns_404() -> None:
    _override(FakeAgentClient(result=success_result()))

    response = client.post("/api/v1/agent/runs/does-not-exist/cancel")

    assert response.status_code == 404


def test_tool_execute_success() -> None:
    run_store, action_store = _override(FakeAgentClient(result=success_result()))
    create_response = client.post("/api/v1/agent/runs", json={"task": "t"})
    run_id = create_response.json()["run_id"]

    response = client.post(
        "/api/v1/agent/tools/execute",
        json={"run_id": run_id, "tool_name": "echo", "input": {"message": "hi"}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"] == {"echoed": "hi"}


def test_tool_execute_unknown_tool_returns_404() -> None:
    _override(FakeAgentClient(result=success_result()))
    create_response = client.post("/api/v1/agent/runs", json={"task": "t"})
    run_id = create_response.json()["run_id"]

    response = client.post(
        "/api/v1/agent/tools/execute",
        json={"run_id": run_id, "tool_name": "does_not_exist", "input": {}},
    )

    assert response.status_code == 404


def test_tool_execute_unknown_run_returns_404() -> None:
    _override(FakeAgentClient(result=success_result()))

    response = client.post(
        "/api/v1/agent/tools/execute",
        json={"run_id": "does-not-exist", "tool_name": "echo", "input": {"message": "hi"}},
    )

    assert response.status_code == 404


def test_tool_execute_rejects_wrong_internal_service_token() -> None:
    from app.core.exceptions import PermissionDeniedError

    _override(FakeAgentClient(result=success_result()))
    create_response = client.post("/api/v1/agent/runs", json={"task": "t"})
    run_id = create_response.json()["run_id"]

    def strict_check(x_internal_service_token: str | None = None) -> None:
        if x_internal_service_token != "expected-secret":
            raise PermissionDeniedError("Invalid or missing internal service token")

    app.dependency_overrides[verify_internal_service] = strict_check

    response = client.post(
        "/api/v1/agent/tools/execute",
        json={"run_id": run_id, "tool_name": "echo", "input": {"message": "hi"}},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
