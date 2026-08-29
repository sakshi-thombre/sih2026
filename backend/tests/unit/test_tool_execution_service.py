"""Unit tests for tool_execution_service — the permission-checked path
Person C's agent service must go through to run any tool."""

import pytest
from pydantic import BaseModel

from app.core.exceptions import NotFoundError, PermissionDeniedError
from app.runs.models import AgentRun
from app.runs.store import InMemoryActionStore, InMemoryRunStore
from app.services.tool_execution_service import execute_tool
from app.tools.base import Tool, ToolRegistry, ToolResult


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


class ManagerOnlyTool(Tool):
    name = "manager_only"
    description = "restricted tool"
    input_schema = EchoInput
    required_role = "manager"

    async def run(self, input_data: BaseModel) -> ToolResult:
        return ToolResult(success=True, data={"ok": True})


class ExplodingTool(Tool):
    name = "exploding"
    description = "always raises"
    input_schema = EchoInput
    required_role = None

    async def run(self, input_data: BaseModel) -> ToolResult:
        raise RuntimeError("boom")


async def _setup(role: str = "engineer") -> tuple[InMemoryRunStore, InMemoryActionStore, ToolRegistry, str]:
    run_store = InMemoryRunStore()
    action_store = InMemoryActionStore()
    registry = ToolRegistry()
    registry.register(EchoTool())
    registry.register(ManagerOnlyTool())
    registry.register(ExplodingTool())

    run = AgentRun(user_id="user-1", role=role, task="test task")
    await run_store.create(run)
    return run_store, action_store, registry, run.run_id


@pytest.mark.anyio
async def test_execute_tool_success() -> None:
    run_store, action_store, registry, run_id = await _setup()

    result = await execute_tool(
        run_id=run_id,
        tool_name="echo",
        tool_input={"message": "hello"},
        run_store=run_store,
        action_store=action_store,
        tool_registry=registry,
    )

    assert result.success is True
    assert result.data == {"echoed": "hello"}


@pytest.mark.anyio
async def test_execute_tool_records_audit_events() -> None:
    run_store, action_store, registry, run_id = await _setup()

    await execute_tool(
        run_id=run_id,
        tool_name="echo",
        tool_input={"message": "hi"},
        run_store=run_store,
        action_store=action_store,
        tool_registry=registry,
    )

    actions = await action_store.list_for_run(run_id)
    event_types = [a.event_type for a in actions]
    assert event_types == ["tool_requested", "tool_completed"]
    # never leaks tool input/output content into audit metadata
    for action in actions:
        assert "message" not in action.metadata
        assert "echoed" not in str(action.metadata)


@pytest.mark.anyio
async def test_execute_tool_unknown_run_raises_not_found() -> None:
    run_store = InMemoryRunStore()
    action_store = InMemoryActionStore()
    registry = ToolRegistry()
    registry.register(EchoTool())

    with pytest.raises(NotFoundError):
        await execute_tool(
            run_id="does-not-exist",
            tool_name="echo",
            tool_input={"message": "hi"},
            run_store=run_store,
            action_store=action_store,
            tool_registry=registry,
        )


@pytest.mark.anyio
async def test_execute_tool_unknown_tool_raises_not_found() -> None:
    run_store, action_store, registry, run_id = await _setup()

    with pytest.raises(NotFoundError):
        await execute_tool(
            run_id=run_id,
            tool_name="does_not_exist",
            tool_input={},
            run_store=run_store,
            action_store=action_store,
            tool_registry=registry,
        )

    actions = await action_store.list_for_run(run_id)
    assert [a.event_type for a in actions] == ["tool_requested", "tool_failed"]


@pytest.mark.anyio
async def test_execute_tool_permission_denied_for_wrong_role() -> None:
    run_store, action_store, registry, run_id = await _setup(role="engineer")

    with pytest.raises(PermissionDeniedError):
        await execute_tool(
            run_id=run_id,
            tool_name="manager_only",
            tool_input={"message": "hi"},
            run_store=run_store,
            action_store=action_store,
            tool_registry=registry,
        )

    actions = await action_store.list_for_run(run_id)
    assert [a.event_type for a in actions] == ["tool_requested", "permission_denied"]


@pytest.mark.anyio
async def test_execute_tool_allowed_for_matching_role() -> None:
    run_store, action_store, registry, run_id = await _setup(role="manager")

    result = await execute_tool(
        run_id=run_id,
        tool_name="manager_only",
        tool_input={"message": "hi"},
        run_store=run_store,
        action_store=action_store,
        tool_registry=registry,
    )

    assert result.success is True


@pytest.mark.anyio
async def test_execute_tool_invalid_input_returns_structured_failure() -> None:
    run_store, action_store, registry, run_id = await _setup()

    result = await execute_tool(
        run_id=run_id,
        tool_name="echo",
        tool_input={"wrong_field": 123},
        run_store=run_store,
        action_store=action_store,
        tool_registry=registry,
    )

    assert result.success is False
    assert result.error is not None


@pytest.mark.anyio
async def test_execute_tool_unexpected_exception_is_caught() -> None:
    run_store, action_store, registry, run_id = await _setup()

    result = await execute_tool(
        run_id=run_id,
        tool_name="exploding",
        tool_input={"message": "hi"},
        run_store=run_store,
        action_store=action_store,
        tool_registry=registry,
    )

    assert result.success is False
    assert "boom" not in (result.error or "")  # raw exception text never leaks


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
