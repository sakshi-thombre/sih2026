"""Task/agent-run orchestration — the layer between the
`/api/v1/agent` routes and (a) Person C's external agent service via
`AgentClient`, and (b) our own in-memory run/action tracking.

This module deliberately contains no reasoning/planning logic: it
manages run lifecycle, calls `AgentClient` exactly once per run, and
records what happened. All task understanding, planning, and
tool-selection intelligence lives in Person C's service.
"""

import logging
from datetime import datetime, timezone

from app.audit.logger import AuditEvent, log_event
from app.clients.agent_client import AgentClient
from app.core.exceptions import (
    InvalidStateError,
    NotFoundError,
    ServiceUnavailableError,
    UpstreamServiceError,
)
from app.runs.models import TERMINAL_STATUSES, AgentRun, RunAction, RunStatus
from app.runs.store import ActionStore, RunStore
from app.schemas.agent import AgentRunRequest

logger = logging.getLogger(__name__)


async def _record(
    action_store: ActionStore, run_id: str, event_type: str, metadata: dict | None = None
) -> None:
    metadata = metadata or {}
    log_event(AuditEvent(event_type=event_type, run_id=run_id, metadata=metadata))
    await action_store.add(RunAction(run_id=run_id, event_type=event_type, metadata=metadata))


async def create_run(
    *,
    task: str,
    context: dict,
    user_id: str,
    role: str,
    unit_id: str = "",
    run_store: RunStore,
    action_store: ActionStore,
) -> AgentRun:
    run = AgentRun(
        user_id=user_id, role=role, unit_id=unit_id, task=task, context=context, status=RunStatus.CREATED
    )
    await run_store.create(run)
    await run_store.compare_and_set_status(run.run_id, RunStatus.CREATED, RunStatus.QUEUED)
    run.status = RunStatus.QUEUED
    await _record(action_store, run.run_id, "run_created", {"user_id": user_id})
    return run


async def execute_run(
    *,
    run_id: str,
    run_store: RunStore,
    action_store: ActionStore,
    agent_client: AgentClient,
) -> None:
    """Scheduled via FastAPI `BackgroundTasks` right after `create_run`.
    Guarded end-to-end by `compare_and_set_status` so a run can never be
    executed twice and a cancelled run can never be overwritten by a
    late-arriving result — see app.runs.store for the exact guarantee.
    """
    started = await run_store.compare_and_set_status(run_id, RunStatus.QUEUED, RunStatus.RUNNING)
    if not started:
        logger.warning("run_execution_skipped_not_queued", extra={"run_id": run_id})
        return

    run = await run_store.get(run_id)
    if run is None:
        return
    run.started_at = datetime.now(timezone.utc)
    await run_store.update(run)
    await _record(action_store, run_id, "run_started")

    request = AgentRunRequest(
        run_id=run.run_id,
        request_id=run.request_id,
        user_id=run.user_id,
        role=run.role,
        task=run.task,
        context=run.context,
    )

    try:
        result = await agent_client.run(request)
    except (ServiceUnavailableError, UpstreamServiceError) as exc:
        if await run_store.compare_and_set_status(run_id, RunStatus.RUNNING, RunStatus.FAILED):
            failed_run = await run_store.get(run_id)
            if failed_run is not None:
                failed_run.completed_at = datetime.now(timezone.utc)
                failed_run.error_code = getattr(exc, "code", "internal_error")
                failed_run.error_message = "Agent service call failed"
                await run_store.update(failed_run)
                await _record(action_store, run_id, "run_failed", {"error_code": failed_run.error_code})
        return

    if result.status == "failed":
        if await run_store.compare_and_set_status(run_id, RunStatus.RUNNING, RunStatus.FAILED):
            failed_run = await run_store.get(run_id)
            if failed_run is not None:
                failed_run.completed_at = datetime.now(timezone.utc)
                failed_run.error_message = result.error_message or "Agent service reported failure"
                await run_store.update(failed_run)
                await _record(action_store, run_id, "run_failed", {})
        return

    if await run_store.compare_and_set_status(run_id, RunStatus.RUNNING, RunStatus.COMPLETED):
        completed_run = await run_store.get(run_id)
        if completed_run is not None:
            completed_run.completed_at = datetime.now(timezone.utc)
            completed_run.answer = result.answer
            completed_run.plan_summary = result.plan_summary
            completed_run.tools_used = result.tools_used
            completed_run.sources = result.sources
            await run_store.update(completed_run)
            await _record(
                action_store,
                run_id,
                "run_completed",
                {"tools_used": result.tools_used, "source_count": len(result.sources)},
            )


async def get_run(run_id: str, run_store: RunStore) -> AgentRun:
    run = await run_store.get(run_id)
    if run is None:
        raise NotFoundError(f"No run found with id '{run_id}'")
    return run


async def list_actions(run_id: str, run_store: RunStore, action_store: ActionStore) -> list[RunAction]:
    run = await run_store.get(run_id)
    if run is None:
        raise NotFoundError(f"No run found with id '{run_id}'")
    return await action_store.list_for_run(run_id)


async def cancel_run(run_id: str, run_store: RunStore, action_store: ActionStore) -> AgentRun:
    """Best-effort: if the agent call is already in flight, we can't
    abort the outbound request itself, but the CAS guard in
    `execute_run` ensures its eventual result is discarded rather than
    overwriting this cancellation."""
    run = await run_store.get(run_id)
    if run is None:
        raise NotFoundError(f"No run found with id '{run_id}'")

    if run.status in TERMINAL_STATUSES:
        raise InvalidStateError(f"Run '{run_id}' is already in a terminal state ({run.status.value})")

    if not await run_store.compare_and_set_status(run_id, run.status, RunStatus.CANCELLED):
        current = await run_store.get(run_id)
        state = current.status.value if current is not None else "unknown"
        raise InvalidStateError(f"Run '{run_id}' could not be cancelled (now in state '{state}')")

    cancelled_run = await run_store.get(run_id)
    assert cancelled_run is not None
    cancelled_run.completed_at = datetime.now(timezone.utc)
    await run_store.update(cancelled_run)
    await _record(action_store, run_id, "run_cancelled")
    return cancelled_run
