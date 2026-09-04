"""Frontend-facing agent orchestration endpoints, plus one internal
endpoint (`/tools/execute`) called by Person C's agent service rather
than the frontend — see `verify_internal_service` for that trust
boundary.

Routes stay thin: authenticate/validate, delegate to
`app.services.task_service` / `app.services.tool_execution_service`,
return the response. No orchestration, planning, or tool logic lives
here.
"""

from fastapi import APIRouter, BackgroundTasks, Depends

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
from app.runs.models import AgentRun
from app.runs.store import ActionStore, RunStore
from app.schemas.agent import (
    CancelRunResponse,
    CreateRunRequest,
    CreateRunResponse,
    RunActionResponse,
    RunActionsResponse,
    RunResponse,
    RunStatusResponse,
    ToolExecuteRequest,
    ToolExecuteResponse,
)
from app.services import task_service, tool_execution_service
from app.tools.base import ToolRegistry

router = APIRouter(prefix="/agent")


def _to_run_response(run: AgentRun) -> RunResponse:
    return RunResponse(
        run_id=run.run_id,
        status=run.status.value,
        task=run.task,
        created_at=run.created_at,
        started_at=run.started_at,
        completed_at=run.completed_at,
        answer=run.answer,
        plan_summary=run.plan_summary,
        tools_used=run.tools_used,
        sources=run.sources,
        error_code=run.error_code,
        error_message=run.error_message,
    )


@router.post("/runs", response_model=CreateRunResponse, status_code=202)
async def create_run(
    request: CreateRunRequest,
    background_tasks: BackgroundTasks,
    user: dict[str, str] = Depends(get_current_user),
    run_store: RunStore = Depends(get_run_store),
    action_store: ActionStore = Depends(get_action_store),
    agent_client: AgentClient = Depends(get_agent_client),
) -> CreateRunResponse:
    run = await task_service.create_run(
        task=request.task,
        context=request.context,
        user_id=user.get("user_id", "unknown"),
        role=user.get("role", ""),
        unit_id=user.get("unit_id", ""),
        run_store=run_store,
        action_store=action_store,
    )
    background_tasks.add_task(
        task_service.execute_run,
        run_id=run.run_id,
        run_store=run_store,
        action_store=action_store,
        agent_client=agent_client,
    )
    return CreateRunResponse(run_id=run.run_id, status=run.status.value)


@router.get("/runs/{run_id}", response_model=RunResponse)
async def get_run(
    run_id: str,
    user: dict[str, str] = Depends(get_current_user),
    run_store: RunStore = Depends(get_run_store),
) -> RunResponse:
    run = await task_service.get_run(run_id, run_store)
    return _to_run_response(run)


@router.get("/runs/{run_id}/status", response_model=RunStatusResponse)
async def get_run_status(
    run_id: str,
    user: dict[str, str] = Depends(get_current_user),
    run_store: RunStore = Depends(get_run_store),
) -> RunStatusResponse:
    run = await task_service.get_run(run_id, run_store)
    return RunStatusResponse(run_id=run.run_id, status=run.status.value)


@router.get("/runs/{run_id}/actions", response_model=RunActionsResponse)
async def get_run_actions(
    run_id: str,
    user: dict[str, str] = Depends(get_current_user),
    run_store: RunStore = Depends(get_run_store),
    action_store: ActionStore = Depends(get_action_store),
) -> RunActionsResponse:
    actions = await task_service.list_actions(run_id, run_store, action_store)
    return RunActionsResponse(
        run_id=run_id,
        actions=[
            RunActionResponse(event_type=a.event_type, timestamp=a.timestamp, metadata=a.metadata)
            for a in actions
        ],
    )


@router.post("/runs/{run_id}/cancel", response_model=CancelRunResponse)
async def cancel_run(
    run_id: str,
    user: dict[str, str] = Depends(get_current_user),
    run_store: RunStore = Depends(get_run_store),
    action_store: ActionStore = Depends(get_action_store),
) -> CancelRunResponse:
    run = await task_service.cancel_run(run_id, run_store, action_store)
    return CancelRunResponse(run_id=run.run_id, status=run.status.value)


@router.post(
    "/tools/execute",
    response_model=ToolExecuteResponse,
    dependencies=[Depends(verify_internal_service)],
)
async def execute_tool(
    request: ToolExecuteRequest,
    run_store: RunStore = Depends(get_service_run_store),
    action_store: ActionStore = Depends(get_service_action_store),
    tool_registry: ToolRegistry = Depends(get_tool_registry),
) -> ToolExecuteResponse:
    """Called by Person C's agent service, not the frontend. The agent
    process never executes a tool directly — every call is routed
    through `ToolRegistry`, permission-checked against the run's role,
    and audited here.

    Uses the service-scoped run/action stores (not `get_run_store`/
    `get_action_store`): this request carries no end-user JWT — it's
    authenticated via `verify_internal_service` instead — so there's
    no user identity to scope the Supabase query by."""
    result = await tool_execution_service.execute_tool(
        run_id=request.run_id,
        tool_name=request.tool_name,
        tool_input=request.input,
        run_store=run_store,
        action_store=action_store,
        tool_registry=tool_registry,
    )
    return ToolExecuteResponse(success=result.success, data=result.data, error=result.error)
