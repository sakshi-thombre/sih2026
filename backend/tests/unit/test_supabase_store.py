"""Unit tests for SupabaseRunStore / SupabaseActionStore. No live
Supabase project required — all HTTP interaction is mocked via
httpx.MockTransport, mirroring tests/unit/test_agent_client.py and
tests/unit/test_llm_ollama_provider.py.

The mocking seam is real, not a test-only shim added to production
code: supabase.AsyncClient accepts an `options.httpx_client`
(supabase/lib/client_options.py::AsyncClientOptions.httpx_client),
which it threads down into the underlying AsyncPostgrestClient
(supabase/_async/client.py::_init_postgrest_client), which uses it as
its request `session` instead of constructing its own
(postgrest/_async/client.py::AsyncPostgrestClient.__init__). Every
request `SupabaseRunStore`/`SupabaseActionStore` make ultimately goes
through `RequestConfig.send`, i.e. `self.session.request(...)`
(postgrest/base_request_builder.py) — exactly the httpx.AsyncClient we
inject here.
"""

import json
from datetime import datetime, timezone

import httpx
import pytest
from supabase import AsyncClient
from supabase.lib.client_options import AsyncClientOptions

from app.core.exceptions import ServiceUnavailableError
from app.rag.base import DocumentChunk
from app.runs.models import AgentRun, RunAction, RunStatus
from app.runs.supabase_store import SupabaseActionStore, SupabaseRunStore, _row_to_run, _run_to_row


def make_supabase_client(handler) -> AsyncClient:
    transport = httpx.MockTransport(handler)
    httpx_client = httpx.AsyncClient(transport=transport)
    options = AsyncClientOptions(httpx_client=httpx_client)
    return AsyncClient("http://localhost:54321", "test-anon-key", options=options)


def make_run(**overrides) -> AgentRun:
    defaults = dict(user_id="user-1", role="engineer", unit_id="", task="do something")
    defaults.update(overrides)
    return AgentRun(**defaults)


def row_for(run: AgentRun, **overrides) -> dict:
    row = _run_to_row(run)
    row["id"] = run.run_id
    row.update(overrides)
    return row


# ---------------------------------------------------------------------------
# SupabaseRunStore.create
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_create_sends_insert_with_correct_row_and_table() -> None:
    run = make_run()
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(201, json=[captured["body"]])

    store = SupabaseRunStore(make_supabase_client(handler))
    await store.create(run)

    assert captured["method"] == "POST"
    assert captured["path"] == "/rest/v1/agent_action_logs"
    assert captured["body"]["id"] == run.run_id
    assert captured["body"]["user_id"] == "user-1"
    assert captured["body"]["role"] == "engineer"
    assert captured["body"]["task_input"] == "do something"
    assert captured["body"]["status"] == "created"


@pytest.mark.anyio
async def test_create_wraps_api_error_as_service_unavailable() -> None:
    run = make_run()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            409,
            json={"message": "duplicate key", "code": "23505", "hint": None, "details": None},
        )

    store = SupabaseRunStore(make_supabase_client(handler))
    with pytest.raises(ServiceUnavailableError) as exc_info:
        await store.create(run)

    assert exc_info.value.status_code == 503
    assert exc_info.value.code == "service_unavailable"


# ---------------------------------------------------------------------------
# SupabaseRunStore.get
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_get_existing_run_returns_deserialized_run() -> None:
    run = make_run(
        answer="the answer",
        plan_summary=["step 1"],
        tools_used=["document_search"],
        sources=[
            DocumentChunk(
                document_id="doc-1",
                filename="sop.txt",
                chunk_id="doc-1:0",
                text="some text",
                score=0.5,
            )
        ],
    )
    row = row_for(run)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/rest/v1/agent_action_logs"
        assert request.url.params["id"] == f"eq.{run.run_id}"
        assert request.url.params["select"] == "*"
        return httpx.Response(200, json=[row])

    store = SupabaseRunStore(make_supabase_client(handler))
    fetched = await store.get(run.run_id)

    assert fetched is not None
    assert fetched.run_id == run.run_id
    assert fetched.user_id == "user-1"
    assert fetched.role == "engineer"
    assert fetched.task == "do something"
    assert fetched.status == RunStatus.CREATED
    assert fetched.answer == "the answer"
    assert fetched.plan_summary == ["step 1"]
    assert fetched.tools_used == ["document_search"]
    assert len(fetched.sources) == 1
    assert fetched.sources[0].document_id == "doc-1"


@pytest.mark.anyio
async def test_get_missing_run_returns_none() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    store = SupabaseRunStore(make_supabase_client(handler))
    assert await store.get("does-not-exist") is None


@pytest.mark.anyio
async def test_get_wraps_connection_failure_as_service_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    store = SupabaseRunStore(make_supabase_client(handler))
    with pytest.raises(ServiceUnavailableError) as exc_info:
        await store.get("run-1")

    assert exc_info.value.status_code == 503


# ---------------------------------------------------------------------------
# SupabaseRunStore.compare_and_set_status
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_compare_and_set_status_succeeds_when_expected_matches() -> None:
    run = make_run()
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        captured["id_filter"] = request.url.params["id"]
        captured["status_filter"] = request.url.params["status"]
        row = row_for(run, status="queued")
        return httpx.Response(200, json=[row])

    store = SupabaseRunStore(make_supabase_client(handler))
    result = await store.compare_and_set_status(run.run_id, RunStatus.CREATED, RunStatus.QUEUED)

    assert result is True
    assert captured["body"] == {"status": "queued"}
    assert captured["id_filter"] == f"eq.{run.run_id}"
    assert captured["status_filter"] == "eq.created"


@pytest.mark.anyio
async def test_compare_and_set_status_fails_when_expected_does_not_match() -> None:
    """PostgreSQL matches zero rows because the WHERE ... AND status =
    'created' clause doesn't hold — postgrest reports this the same
    way it reports "no rows": an empty representation array, not an
    error."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    store = SupabaseRunStore(make_supabase_client(handler))
    result = await store.compare_and_set_status("run-1", RunStatus.CREATED, RunStatus.RUNNING)

    assert result is False


@pytest.mark.anyio
async def test_compare_and_set_status_on_missing_run_returns_false() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    store = SupabaseRunStore(make_supabase_client(handler))
    result = await store.compare_and_set_status("does-not-exist", RunStatus.CREATED, RunStatus.QUEUED)

    assert result is False


# ---------------------------------------------------------------------------
# SupabaseRunStore.update
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_update_sends_patch_without_status_field() -> None:
    run = make_run(answer="final answer", completed_at=datetime.now(timezone.utc))
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        captured["id_filter"] = request.url.params["id"]
        return httpx.Response(200, json=[row_for(run)])

    store = SupabaseRunStore(make_supabase_client(handler))
    await store.update(run)

    assert "status" not in captured["body"]
    assert captured["body"]["final_output"] == "final answer"
    assert captured["id_filter"] == f"eq.{run.run_id}"


@pytest.mark.anyio
async def test_update_on_missing_run_does_not_raise() -> None:
    run = make_run()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    store = SupabaseRunStore(make_supabase_client(handler))
    await store.update(run)  # no matching row updated, but no exception either


# ---------------------------------------------------------------------------
# SupabaseActionStore.add
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_action_store_add_calls_rpc_with_correct_params() -> None:
    action = RunAction(run_id="run-1", event_type="run_started", metadata={"foo": "bar"})
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=None)

    store = SupabaseActionStore(make_supabase_client(handler))
    await store.add(action)

    assert captured["method"] == "POST"
    assert captured["path"] == "/rest/v1/rpc/append_agent_action"
    assert captured["body"] == {
        "p_run_id": "run-1",
        "p_event_type": "run_started",
        "p_metadata": {"foo": "bar"},
    }


@pytest.mark.anyio
async def test_action_store_add_wraps_api_error_as_service_unavailable() -> None:
    action = RunAction(run_id="run-1", event_type="run_started")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            500,
            json={"message": "boom", "code": "XX000", "hint": None, "details": None},
        )

    store = SupabaseActionStore(make_supabase_client(handler))
    with pytest.raises(ServiceUnavailableError):
        await store.add(action)


# ---------------------------------------------------------------------------
# SupabaseActionStore.list_for_run
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_action_store_list_for_run_returns_correctly_associated_actions() -> None:
    row = {
        "actions": [
            {"event_type": "run_created", "timestamp": "2026-01-01T00:00:00+00:00", "metadata": {}},
            {
                "event_type": "tool_called",
                "timestamp": "2026-01-01T00:01:00+00:00",
                "metadata": {"tool": "document_search"},
            },
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["id"] == "eq.run-1"
        assert request.url.params["select"] == "actions"
        return httpx.Response(200, json=[row])

    store = SupabaseActionStore(make_supabase_client(handler))
    actions = await store.list_for_run("run-1")

    assert [a.event_type for a in actions] == ["run_created", "tool_called"]
    # Every action is associated with the run it was looked up for, even
    # though the stored jsonb entries themselves carry no run_id.
    assert all(a.run_id == "run-1" for a in actions)
    assert actions[1].metadata == {"tool": "document_search"}


@pytest.mark.anyio
async def test_action_store_list_for_unknown_run_returns_empty_list() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    store = SupabaseActionStore(make_supabase_client(handler))
    assert await store.list_for_run("unknown") == []


# ---------------------------------------------------------------------------
# Serialization / deserialization of stored fields
# ---------------------------------------------------------------------------


def test_run_to_row_serializes_status_and_timestamps_to_plain_json_types() -> None:
    run = make_run(
        status=RunStatus.RUNNING,
        started_at=datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        completed_at=None,
        sources=[
            DocumentChunk(
                document_id="doc-1",
                filename="sop.txt",
                chunk_id="doc-1:0",
                text="some text",
                score=0.5,
                page_number=3,
            )
        ],
    )

    row = _run_to_row(run)

    assert row["status"] == "running"
    assert row["started_at"] == run.started_at.isoformat()
    assert row["completed_at"] is None
    assert row["created_at"] == run.created_at.isoformat()
    assert row["sources"] == [
        {
            "document_id": "doc-1",
            "filename": "sop.txt",
            "chunk_id": "doc-1:0",
            "text": "some text",
            "score": 0.5,
            "unit_id": None,
            "page_number": 3,
            "chunk_index": None,
        }
    ]
    # request_id/user_id/role/task_input map from request_id/user_id/role/task —
    # not identical field names, so this is worth pinning down explicitly.
    assert row["request_id"] == run.request_id
    assert row["task_input"] == run.task


def test_row_to_run_deserializes_status_and_sources_to_typed_fields() -> None:
    row = {
        "id": "run-1",
        "request_id": "req-1",
        "user_id": "user-1",
        "role": "manager",
        "task_input": "investigate incident",
        "context": {"unit": "3"},
        "status": "failed",
        "created_at": "2026-01-01T00:00:00+00:00",
        "started_at": "2026-01-01T00:01:00+00:00",
        "completed_at": None,
        "final_output": None,
        "plan": ["step 1", "step 2"],
        "tools_used": ["document_search"],
        "sources": [
            {
                "document_id": "doc-1",
                "filename": "sop.txt",
                "chunk_id": "doc-1:0",
                "text": "some text",
                "score": 0.5,
                "page_number": None,
                "chunk_index": None,
            }
        ],
        "error_code": "upstream_error",
        "error_message": "agent service timed out",
    }

    run = _row_to_run(row)

    assert run.run_id == "run-1"
    assert run.request_id == "req-1"
    assert run.status == RunStatus.FAILED
    assert isinstance(run.status, RunStatus)
    assert run.context == {"unit": "3"}
    assert run.plan_summary == ["step 1", "step 2"]
    assert len(run.sources) == 1
    assert isinstance(run.sources[0], DocumentChunk)
    assert run.sources[0].score == 0.5
    assert run.error_code == "upstream_error"
    assert run.error_message == "agent service timed out"


def test_row_to_run_defaults_missing_optional_fields() -> None:
    """request_id/task_input/context/plan/tools_used/sources are all
    read with `.get(...) or <default>` in _row_to_run — this pins down
    that a row missing them (e.g. a legacy row, or one written before a
    field existed) deserializes cleanly instead of raising."""
    row = {
        "id": "run-1",
        "user_id": "user-1",
        "role": "engineer",
        "status": "created",
        "created_at": "2026-01-01T00:00:00+00:00",
    }

    run = _row_to_run(row)

    assert run.request_id == "run-1"  # falls back to row["id"]
    assert run.task == ""
    assert run.context == {}
    assert run.plan_summary == []
    assert run.tools_used == []
    assert run.sources == []
    assert run.answer is None
    assert run.error_code is None


def test_run_to_row_then_row_to_run_round_trip_preserves_fields() -> None:
    run = make_run(
        status=RunStatus.COMPLETED,
        started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        completed_at=datetime(2026, 1, 1, 0, 5, tzinfo=timezone.utc),
        answer="done",
        plan_summary=["a", "b"],
        tools_used=["document_search"],
    )

    row = row_for(run)
    round_tripped = _row_to_run(row)

    assert round_tripped.run_id == run.run_id
    assert round_tripped.request_id == run.request_id
    assert round_tripped.user_id == run.user_id
    assert round_tripped.role == run.role
    assert round_tripped.task == run.task
    assert round_tripped.status == run.status
    assert round_tripped.started_at == run.started_at
    assert round_tripped.completed_at == run.completed_at
    assert round_tripped.answer == run.answer
    assert round_tripped.plan_summary == run.plan_summary
    assert round_tripped.tools_used == run.tools_used


def test_run_to_row_then_row_to_run_round_trip_preserves_non_empty_unit_id() -> None:
    """unit_id is the trusted context tool_execution_service reads back
    to enforce document search isolation (see app.services.
    tool_execution_service) — a round-trip that silently dropped or
    mangled it would reopen the cross-unit gap that field exists to
    close."""
    run = make_run(unit_id="11111111-1111-1111-1111-111111111111")

    row = row_for(run)
    round_tripped = _row_to_run(row)

    assert round_tripped.unit_id == "11111111-1111-1111-1111-111111111111"


def test_run_to_row_serializes_empty_unit_id_as_null() -> None:
    """agent_action_logs.unit_id is a `uuid` column (see
    supabase/migrations/0005_agent_run_unit_id.sql) — sending "" would
    be rejected by Postgres, so an unassigned unit_id (e.g. a manager's
    run) must be written as SQL NULL, not the empty string."""
    run = make_run(unit_id="")

    row = _run_to_row(run)

    assert row["unit_id"] is None


def test_row_to_run_restores_null_unit_id_as_empty_string() -> None:
    row = row_for(make_run(unit_id=""))

    round_tripped = _row_to_run(row)

    assert round_tripped.unit_id == ""


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
