"""Two distinct sets of schemas, kept separate on purpose:

- `AgentRunRequest`/`AgentRunResult`: the versioned wire contract
  between this backend and Person C's external agent service.
- Everything else: request/response shapes for the frontend-facing
  `/api/v1/agent` API.

Changing the frontend API should never require Person C to change
their contract, and vice versa.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.rag.base import DocumentChunk

AGENT_CONTRACT_VERSION = "v1"


class AgentRunRequest(BaseModel):
    """Sent to Person C's agent service to start a run."""

    contract_version: str = AGENT_CONTRACT_VERSION
    run_id: str
    request_id: str
    user_id: str
    role: str
    task: str = Field(..., min_length=1, max_length=8000)
    context: dict[str, Any] = Field(default_factory=dict)


class AgentRunResult(BaseModel):
    """Returned by Person C's agent service when a run finishes.

    No field for a raw reasoning/chain-of-thought trace — only a safe,
    high-level `plan_summary`. `sources` reuses the existing
    `DocumentChunk` schema rather than inventing a parallel citation
    shape.
    """

    contract_version: str = AGENT_CONTRACT_VERSION
    run_id: str
    status: Literal["completed", "failed"]
    answer: str | None = None
    plan_summary: list[str] = Field(default_factory=list)
    tools_used: list[str] = Field(default_factory=list)
    sources: list[DocumentChunk] = Field(default_factory=list)
    error_message: str | None = None


# ---- Frontend-facing /api/v1/agent API schemas ----


class CreateRunRequest(BaseModel):
    task: str = Field(..., min_length=1, max_length=8000)
    context: dict[str, Any] = Field(default_factory=dict)


class CreateRunResponse(BaseModel):
    run_id: str
    status: str


class RunResponse(BaseModel):
    run_id: str
    status: str
    task: str
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    answer: str | None = None
    plan_summary: list[str] = Field(default_factory=list)
    tools_used: list[str] = Field(default_factory=list)
    sources: list[DocumentChunk] = Field(default_factory=list)
    error_code: str | None = None
    error_message: str | None = None


class RunStatusResponse(BaseModel):
    run_id: str
    status: str


class RunActionResponse(BaseModel):
    event_type: str
    timestamp: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class RunActionsResponse(BaseModel):
    run_id: str
    actions: list[RunActionResponse]


class CancelRunResponse(BaseModel):
    run_id: str
    status: str


class ToolExecuteRequest(BaseModel):
    run_id: str
    tool_name: str
    input: dict[str, Any] = Field(default_factory=dict)


class ToolExecuteResponse(BaseModel):
    success: bool
    data: Any = None
    error: str | None = None
