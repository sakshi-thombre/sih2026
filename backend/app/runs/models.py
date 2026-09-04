"""Domain models for agent runs — the backend's own tracking of a
task's lifecycle. Distinct from `app.schemas.agent.AgentRunRequest` /
`AgentRunResult`, which are the wire contract with Person C's service:
what we choose to track internally can change without touching that
contract, and vice versa.
"""

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from app.rag.base import DocumentChunk


class RunStatus(str, Enum):
    CREATED = "created"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_STATUSES = {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED}


class AgentRun(BaseModel):
    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    role: str
    # Authenticated caller's unit at run-creation time (see get_current_user).
    # Persisted here, not read from the agent service's tool-execution
    # request, so a tool like document_search can enforce unit isolation
    # from a trusted source even though /tools/execute carries no end-user
    # identity of its own — see app.services.tool_execution_service.
    unit_id: str = ""
    task: str
    context: dict[str, Any] = Field(default_factory=dict)
    status: RunStatus = RunStatus.CREATED
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    completed_at: datetime | None = None

    # Populated from AgentRunResult once Person C's service responds.
    # No field for a raw reasoning/chain-of-thought trace — only the
    # safe, high-level summary the contract provides.
    answer: str | None = None
    plan_summary: list[str] = Field(default_factory=list)
    tools_used: list[str] = Field(default_factory=list)
    sources: list[DocumentChunk] = Field(default_factory=list)

    error_code: str | None = None
    error_message: str | None = None


class RunAction(BaseModel):
    """A single safe, structured event in a run's history — backs
    GET /api/v1/agent/runs/{run_id}/actions. Metadata must never
    contain task text, tool input/output content, or answer text;
    see the callers in app.services for what's actually recorded."""

    run_id: str
    event_type: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)
