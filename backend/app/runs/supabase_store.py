"""Supabase-backed `RunStore`/`ActionStore`, persisted in the existing
`agent_action_logs` table rather than new `agent_runs`/
`agent_run_actions` tables — see
supabase/migrations/0004_agent_run_tracking.sql for the columns and
RLS policy this relies on, and for why a per-run `actions` jsonb
column (appended to via the `append_agent_action` RPC) stands in for
a separate action-log table.

Every instance simply wraps whichever `supabase.AsyncClient` it's
given (see app.db.session) — this module has no opinion on whether
that client is scoped to an end user's own JWT or the service-role
key; Row Level Security (or its deliberate absence, for the
service-role case) is what actually decides which rows a given call
can see or change.
"""

from typing import Any

from postgrest.exceptions import APIError
from supabase import AsyncClient

from app.core.exceptions import ServiceUnavailableError
from app.rag.base import DocumentChunk
from app.runs.models import AgentRun, RunAction, RunStatus
from app.runs.store import ActionStore, RunStore

_TABLE = "agent_action_logs"


def _row_to_run(row: dict[str, Any]) -> AgentRun:
    return AgentRun(
        run_id=row["id"],
        request_id=row.get("request_id") or row["id"],
        user_id=row["user_id"],
        role=row["role"],
        task=row.get("task_input") or "",
        context=row.get("context") or {},
        status=RunStatus(row["status"]),
        created_at=row["created_at"],
        started_at=row.get("started_at"),
        completed_at=row.get("completed_at"),
        answer=row.get("final_output"),
        plan_summary=row.get("plan") or [],
        tools_used=row.get("tools_used") or [],
        sources=[DocumentChunk(**source) for source in (row.get("sources") or [])],
        error_code=row.get("error_code"),
        error_message=row.get("error_message"),
    )


def _run_to_row(run: AgentRun) -> dict[str, Any]:
    return {
        "request_id": run.request_id,
        "user_id": run.user_id,
        "role": run.role,
        "task_input": run.task,
        "context": run.context,
        "status": run.status.value,
        "created_at": run.created_at.isoformat(),
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "final_output": run.answer,
        "plan": run.plan_summary,
        "tools_used": run.tools_used,
        "sources": [source.model_dump(mode="json") for source in run.sources],
        "error_code": run.error_code,
        "error_message": run.error_message,
    }


async def _execute(builder: Any) -> Any:
    """Runs a postgrest query builder and translates connectivity/API
    failures into the same `ServiceUnavailableError` other external
    dependencies (Ollama, the agent service) raise on this kind of
    failure, rather than letting a raw postgrest exception escape."""
    try:
        return await builder.execute()
    except APIError as exc:
        raise ServiceUnavailableError("Supabase request failed") from exc
    except Exception as exc:
        raise ServiceUnavailableError("Supabase is unreachable") from exc


class SupabaseRunStore(RunStore):
    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    async def create(self, run: AgentRun) -> None:
        row = _run_to_row(run)
        row["id"] = run.run_id
        await _execute(self._client.table(_TABLE).insert(row))

    async def get(self, run_id: str) -> AgentRun | None:
        response = await _execute(
            self._client.table(_TABLE).select("*").eq("id", run_id).maybe_single()
        )
        if response is None or response.data is None:
            return None
        return _row_to_run(response.data)

    async def compare_and_set_status(
        self, run_id: str, expected: RunStatus, new: RunStatus
    ) -> bool:
        response = await _execute(
            self._client.table(_TABLE)
            .update({"status": new.value})
            .eq("id", run_id)
            .eq("status", expected.value)
        )
        return bool(response.data)

    async def update(self, run: AgentRun) -> None:
        row = _run_to_row(run)
        row.pop("status")  # status only ever changes via compare_and_set_status
        await _execute(self._client.table(_TABLE).update(row).eq("id", run.run_id))


class SupabaseActionStore(ActionStore):
    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    async def add(self, action: RunAction) -> None:
        # A single atomic UPDATE ... SET actions = actions || jsonb(...),
        # done in Postgres (see the RPC in migration 0004) rather than a
        # read-modify-write here, so concurrent tool calls against the
        # same run can't silently drop each other's action records.
        await _execute(
            self._client.rpc(
                "append_agent_action",
                {
                    "p_run_id": action.run_id,
                    "p_event_type": action.event_type,
                    "p_metadata": action.metadata,
                },
            )
        )

    async def list_for_run(self, run_id: str) -> list[RunAction]:
        response = await _execute(
            self._client.table(_TABLE).select("actions").eq("id", run_id).maybe_single()
        )
        if response is None or response.data is None:
            return []
        return [
            RunAction(
                run_id=run_id,
                event_type=entry["event_type"],
                timestamp=entry["timestamp"],
                metadata=entry.get("metadata", {}),
            )
            for entry in (response.data.get("actions") or [])
        ]
