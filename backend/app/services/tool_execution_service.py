"""Tool execution service — the permission-checked path Person C's
agent service must go through to run any tool. This is called by
POST /api/v1/agent/tools/execute and is the single enforcement point:
the agent process itself never gets direct filesystem/SQL/shell/
network access, only whatever a registered Tool exposes, and only if
the run's role satisfies the tool's `required_role`.

Every attempt (requested, denied, completed, failed) is recorded via
the existing audit mechanism plus the run's action history — but never
with the tool's actual input or output content, only names/outcomes.
"""

import logging

from pydantic import ValidationError

from app.audit.logger import AuditEvent, log_event
from app.core.exceptions import NotFoundError, PermissionDeniedError
from app.runs.models import RunAction
from app.runs.store import ActionStore, RunStore
from app.tools.base import ToolRegistry, ToolResult

logger = logging.getLogger(__name__)


async def _record(action_store: ActionStore, run_id: str, event_type: str, metadata: dict) -> None:
    log_event(AuditEvent(event_type=event_type, run_id=run_id, metadata=metadata))
    await action_store.add(RunAction(run_id=run_id, event_type=event_type, metadata=metadata))


async def execute_tool(
    *,
    run_id: str,
    tool_name: str,
    tool_input: dict,
    run_store: RunStore,
    action_store: ActionStore,
    tool_registry: ToolRegistry,
) -> ToolResult:
    run = await run_store.get(run_id)
    if run is None:
        raise NotFoundError(f"No run found with id '{run_id}'")

    await _record(action_store, run_id, "tool_requested", {"tool_name": tool_name})

    tool = tool_registry.get(tool_name)
    if tool is None:
        await _record(
            action_store, run_id, "tool_failed", {"tool_name": tool_name, "reason": "unknown_tool"}
        )
        raise NotFoundError(f"No tool registered with name '{tool_name}'")

    if tool.required_role is not None and run.role != tool.required_role:
        await _record(
            action_store,
            run_id,
            "permission_denied",
            {"tool_name": tool_name, "required_role": tool.required_role},
        )
        raise PermissionDeniedError(f"Tool '{tool_name}' requires role '{tool.required_role}'")

    try:
        validated_input = tool.input_schema.model_validate(tool_input)
    except ValidationError:
        await _record(
            action_store, run_id, "tool_failed", {"tool_name": tool_name, "reason": "invalid_input"}
        )
        return ToolResult(success=False, error="Tool input failed validation")

    try:
        result = await tool.run(validated_input)
    except Exception:
        logger.exception("tool_execution_unexpected_error", extra={"tool_name": tool_name})
        await _record(
            action_store, run_id, "tool_failed", {"tool_name": tool_name, "reason": "unexpected_error"}
        )
        return ToolResult(success=False, error="Tool execution failed unexpectedly")

    await _record(
        action_store,
        run_id,
        "tool_completed" if result.success else "tool_failed",
        {"tool_name": tool_name, "success": result.success},
    )
    return result
