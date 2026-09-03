"""Unit tests for InMemoryRunStore / InMemoryActionStore — lifecycle
transitions and the concurrency guard that prevents a run from being
executed twice."""

import asyncio

import pytest

from app.runs.models import AgentRun, RunAction, RunStatus
from app.runs.store import InMemoryActionStore, InMemoryRunStore


def make_run(**overrides) -> AgentRun:
    defaults = dict(user_id="user-1", role="engineer", task="do something")
    defaults.update(overrides)
    return AgentRun(**defaults)


@pytest.mark.anyio
async def test_create_and_get_round_trip() -> None:
    store = InMemoryRunStore()
    run = make_run()
    await store.create(run)

    fetched = await store.get(run.run_id)
    assert fetched is not None
    assert fetched.run_id == run.run_id
    assert fetched.status == RunStatus.CREATED


@pytest.mark.anyio
async def test_get_unknown_run_returns_none() -> None:
    store = InMemoryRunStore()
    assert await store.get("does-not-exist") is None


@pytest.mark.anyio
async def test_get_returns_independent_copy() -> None:
    store = InMemoryRunStore()
    run = make_run()
    await store.create(run)

    fetched = await store.get(run.run_id)
    assert fetched is not None
    fetched.task = "mutated locally"

    fetched_again = await store.get(run.run_id)
    assert fetched_again is not None
    assert fetched_again.task == "do something"


@pytest.mark.anyio
async def test_compare_and_set_status_succeeds_when_expected_matches() -> None:
    store = InMemoryRunStore()
    run = make_run()
    await store.create(run)

    result = await store.compare_and_set_status(run.run_id, RunStatus.CREATED, RunStatus.QUEUED)
    assert result is True

    fetched = await store.get(run.run_id)
    assert fetched is not None
    assert fetched.status == RunStatus.QUEUED


@pytest.mark.anyio
async def test_compare_and_set_status_fails_when_expected_does_not_match() -> None:
    store = InMemoryRunStore()
    run = make_run()
    await store.create(run)
    await store.compare_and_set_status(run.run_id, RunStatus.CREATED, RunStatus.QUEUED)

    result = await store.compare_and_set_status(run.run_id, RunStatus.CREATED, RunStatus.RUNNING)
    assert result is False

    fetched = await store.get(run.run_id)
    assert fetched is not None
    assert fetched.status == RunStatus.QUEUED


@pytest.mark.anyio
async def test_compare_and_set_status_on_unknown_run_returns_false() -> None:
    store = InMemoryRunStore()
    result = await store.compare_and_set_status("missing", RunStatus.CREATED, RunStatus.QUEUED)
    assert result is False


@pytest.mark.anyio
async def test_update_preserves_status_even_if_stale_object_has_different_status() -> None:
    store = InMemoryRunStore()
    run = make_run()
    await store.create(run)
    await store.compare_and_set_status(run.run_id, RunStatus.CREATED, RunStatus.QUEUED)

    stale = await store.get(run.run_id)
    assert stale is not None
    stale.status = RunStatus.COMPLETED  # local mutation only, never went through CAS
    stale.answer = "some answer"
    await store.update(stale)

    fetched = await store.get(run.run_id)
    assert fetched is not None
    assert fetched.status == RunStatus.QUEUED  # unaffected by the stale object's status
    assert fetched.answer == "some answer"  # non-status fields still persisted


@pytest.mark.anyio
async def test_update_on_unknown_run_is_a_no_op() -> None:
    store = InMemoryRunStore()
    run = make_run()
    await store.update(run)  # should not raise
    assert await store.get(run.run_id) is None


@pytest.mark.anyio
async def test_concurrent_compare_and_set_only_one_winner() -> None:
    """The core duplicate-execution protection guarantee: if many
    callers race to transition the same run out of QUEUED, exactly one
    succeeds."""
    store = InMemoryRunStore()
    run = make_run()
    await store.create(run)
    await store.compare_and_set_status(run.run_id, RunStatus.CREATED, RunStatus.QUEUED)

    results = await asyncio.gather(
        *[
            store.compare_and_set_status(run.run_id, RunStatus.QUEUED, RunStatus.RUNNING)
            for _ in range(10)
        ]
    )

    assert results.count(True) == 1
    assert results.count(False) == 9


@pytest.mark.anyio
async def test_action_store_add_and_list_for_run() -> None:
    store = InMemoryActionStore()
    await store.add(RunAction(run_id="run-1", event_type="run_created"))
    await store.add(RunAction(run_id="run-1", event_type="run_started"))
    await store.add(RunAction(run_id="run-2", event_type="run_created"))

    actions = await store.list_for_run("run-1")
    assert [a.event_type for a in actions] == ["run_created", "run_started"]


@pytest.mark.anyio
async def test_action_store_list_for_unknown_run_returns_empty_list() -> None:
    store = InMemoryActionStore()
    assert await store.list_for_run("unknown") == []


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
