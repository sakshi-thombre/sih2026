"""Unit tests for task_service — run lifecycle, AgentClient integration
(mocked, never a real Person C service), duplicate-execution
protection, and cancellation."""

import asyncio

import pytest

from app.clients.agent_client import AgentClient
from app.core.exceptions import InvalidStateError, NotFoundError, ServiceUnavailableError
from app.runs.models import RunStatus
from app.runs.store import InMemoryActionStore, InMemoryRunStore
from app.schemas.agent import AgentRunRequest, AgentRunResult
from app.services import task_service


class FakeAgentClient(AgentClient):
    def __init__(self, result: AgentRunResult | None = None, error: Exception | None = None) -> None:
        self._result = result
        self._error = error
        self.call_count = 0
        self._delay = 0.0

    async def run(self, request: AgentRunRequest) -> AgentRunResult:
        self.call_count += 1
        if self._delay:
            await asyncio.sleep(self._delay)
        if self._error is not None:
            raise self._error
        assert self._result is not None
        return self._result.model_copy(update={"run_id": request.run_id})


def success_result() -> AgentRunResult:
    return AgentRunResult(
        run_id="placeholder",
        status="completed",
        answer="The answer.",
        plan_summary=["step one", "step two"],
        tools_used=["document_search"],
        sources=[],
    )


@pytest.mark.anyio
async def test_create_run_starts_in_queued_state() -> None:
    run_store = InMemoryRunStore()
    action_store = InMemoryActionStore()

    run = await task_service.create_run(
        task="find safety incidents",
        context={},
        user_id="user-1",
        role="engineer",
        run_store=run_store,
        action_store=action_store,
    )

    assert run.status == RunStatus.QUEUED
    stored = await run_store.get(run.run_id)
    assert stored is not None
    assert stored.status == RunStatus.QUEUED

    actions = await action_store.list_for_run(run.run_id)
    assert [a.event_type for a in actions] == ["run_created"]


@pytest.mark.anyio
async def test_execute_run_success_transitions_to_completed() -> None:
    run_store = InMemoryRunStore()
    action_store = InMemoryActionStore()
    run = await task_service.create_run(
        task="t", context={}, user_id="u", role="engineer", run_store=run_store, action_store=action_store
    )
    client = FakeAgentClient(result=success_result())

    await task_service.execute_run(
        run_id=run.run_id, run_store=run_store, action_store=action_store, agent_client=client
    )

    final = await run_store.get(run.run_id)
    assert final is not None
    assert final.status == RunStatus.COMPLETED
    assert final.answer == "The answer."
    assert final.tools_used == ["document_search"]
    assert final.completed_at is not None

    actions = await action_store.list_for_run(run.run_id)
    event_types = [a.event_type for a in actions]
    assert event_types == ["run_created", "run_started", "run_completed"]


@pytest.mark.anyio
async def test_execute_run_agent_reports_failure() -> None:
    run_store = InMemoryRunStore()
    action_store = InMemoryActionStore()
    run = await task_service.create_run(
        task="t", context={}, user_id="u", role="engineer", run_store=run_store, action_store=action_store
    )
    failure_result = AgentRunResult(run_id=run.run_id, status="failed", error_message="agent gave up")
    client = FakeAgentClient(result=failure_result)

    await task_service.execute_run(
        run_id=run.run_id, run_store=run_store, action_store=action_store, agent_client=client
    )

    final = await run_store.get(run.run_id)
    assert final is not None
    assert final.status == RunStatus.FAILED
    assert final.error_message == "agent gave up"


@pytest.mark.anyio
async def test_execute_run_agent_client_unreachable() -> None:
    run_store = InMemoryRunStore()
    action_store = InMemoryActionStore()
    run = await task_service.create_run(
        task="t", context={}, user_id="u", role="engineer", run_store=run_store, action_store=action_store
    )
    client = FakeAgentClient(error=ServiceUnavailableError("Agent service is unreachable"))

    await task_service.execute_run(
        run_id=run.run_id, run_store=run_store, action_store=action_store, agent_client=client
    )

    final = await run_store.get(run.run_id)
    assert final is not None
    assert final.status == RunStatus.FAILED
    assert final.error_code == "service_unavailable"
    # never leaks the raw exception message into the stored run
    assert final.error_message == "Agent service call failed"


@pytest.mark.anyio
async def test_execute_run_is_a_no_op_if_run_not_queued() -> None:
    """Simulates execute_run being invoked for a run that's already
    running/completed — must not call the agent client again."""
    run_store = InMemoryRunStore()
    action_store = InMemoryActionStore()
    run = await task_service.create_run(
        task="t", context={}, user_id="u", role="engineer", run_store=run_store, action_store=action_store
    )
    await run_store.compare_and_set_status(run.run_id, RunStatus.QUEUED, RunStatus.RUNNING)
    client = FakeAgentClient(result=success_result())

    await task_service.execute_run(
        run_id=run.run_id, run_store=run_store, action_store=action_store, agent_client=client
    )

    assert client.call_count == 0


@pytest.mark.anyio
async def test_concurrent_execute_run_calls_agent_client_exactly_once() -> None:
    """Duplicate-execution protection: even if execute_run is triggered
    concurrently for the same run_id, the agent service is called
    exactly once."""
    run_store = InMemoryRunStore()
    action_store = InMemoryActionStore()
    run = await task_service.create_run(
        task="t", context={}, user_id="u", role="engineer", run_store=run_store, action_store=action_store
    )
    client = FakeAgentClient(result=success_result())
    client._delay = 0.05

    await asyncio.gather(
        *[
            task_service.execute_run(
                run_id=run.run_id, run_store=run_store, action_store=action_store, agent_client=client
            )
            for _ in range(5)
        ]
    )

    assert client.call_count == 1
    final = await run_store.get(run.run_id)
    assert final is not None
    assert final.status == RunStatus.COMPLETED


@pytest.mark.anyio
async def test_get_run_unknown_raises_not_found() -> None:
    run_store = InMemoryRunStore()
    with pytest.raises(NotFoundError):
        await task_service.get_run("missing", run_store)


@pytest.mark.anyio
async def test_list_actions_unknown_run_raises_not_found() -> None:
    run_store = InMemoryRunStore()
    action_store = InMemoryActionStore()
    with pytest.raises(NotFoundError):
        await task_service.list_actions("missing", run_store, action_store)


@pytest.mark.anyio
async def test_cancel_run_from_queued() -> None:
    run_store = InMemoryRunStore()
    action_store = InMemoryActionStore()
    run = await task_service.create_run(
        task="t", context={}, user_id="u", role="engineer", run_store=run_store, action_store=action_store
    )

    cancelled = await task_service.cancel_run(run.run_id, run_store, action_store)

    assert cancelled.status == RunStatus.CANCELLED
    actions = await action_store.list_for_run(run.run_id)
    assert "run_cancelled" in [a.event_type for a in actions]


@pytest.mark.anyio
async def test_cancel_run_already_terminal_raises_invalid_state() -> None:
    run_store = InMemoryRunStore()
    action_store = InMemoryActionStore()
    run = await task_service.create_run(
        task="t", context={}, user_id="u", role="engineer", run_store=run_store, action_store=action_store
    )
    client = FakeAgentClient(result=success_result())
    await task_service.execute_run(
        run_id=run.run_id, run_store=run_store, action_store=action_store, agent_client=client
    )

    with pytest.raises(InvalidStateError):
        await task_service.cancel_run(run.run_id, run_store, action_store)


@pytest.mark.anyio
async def test_cancel_run_unknown_raises_not_found() -> None:
    run_store = InMemoryRunStore()
    action_store = InMemoryActionStore()
    with pytest.raises(NotFoundError):
        await task_service.cancel_run("missing", run_store, action_store)


@pytest.mark.anyio
async def test_cancelled_run_is_not_overwritten_by_late_agent_result() -> None:
    """If a run is cancelled while the agent call is in flight, the
    eventual (successful) result must not resurrect it as completed."""
    run_store = InMemoryRunStore()
    action_store = InMemoryActionStore()
    run = await task_service.create_run(
        task="t", context={}, user_id="u", role="engineer", run_store=run_store, action_store=action_store
    )
    client = FakeAgentClient(result=success_result())
    client._delay = 0.1

    execute_task = asyncio.create_task(
        task_service.execute_run(
            run_id=run.run_id, run_store=run_store, action_store=action_store, agent_client=client
        )
    )
    await asyncio.sleep(0.02)  # let execute_run flip QUEUED -> RUNNING first
    cancelled = await task_service.cancel_run(run.run_id, run_store, action_store)
    assert cancelled.status == RunStatus.CANCELLED

    await execute_task  # let the (now-discarded) agent result arrive

    final = await run_store.get(run.run_id)
    assert final is not None
    assert final.status == RunStatus.CANCELLED
    assert final.answer is None


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
