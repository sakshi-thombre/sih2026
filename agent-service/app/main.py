from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from app.agent import Agent
from app.config import settings


app = FastAPI(
    title="Sovereign Agent Service",
    description="On-premise Agentic AI Service",
    version="1.1.0",
)
agent = Agent()


class AgentRunRequest(BaseModel):
    contract_version: str = "v1"
    run_id: str
    request_id: str
    user_id: str
    role: str
    task: str = Field(..., min_length=1, max_length=8000)
    context: dict[str, Any] = Field(default_factory=dict)


class AgentRunResult(BaseModel):
    contract_version: str = "v1"
    run_id: str
    status: str
    answer: str | None = None
    plan_summary: list[str] = Field(default_factory=list)
    tools_used: list[str] = Field(default_factory=list)
    sources: list[Any] = Field(default_factory=list)
    error_message: str | None = None


def verify_backend_service(x_internal_service_token: str | None) -> None:
    # Development may omit the token. Any configured token is always enforced.
    if settings.internal_service_token and x_internal_service_token != settings.internal_service_token:
        raise HTTPException(status_code=403, detail="Invalid or missing internal service token")


@app.get("/")
async def root():
    return {"status": "Agent Service is running", "backend_tools": "enabled"}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/agent/run", response_model=AgentRunResult)
async def run_agent(
    request: AgentRunRequest,
    x_internal_service_token: str | None = Header(default=None),
):
    verify_backend_service(x_internal_service_token)

    try:
        plan = await agent.create_plan(request.task, request.context)
        results = await agent.execute_plan(request.run_id, plan)
        answer = await agent.generate_final_answer(request.task, results)

        plan_summary = [step.description for step in plan.steps if step.description]
        tools_used = []
        for step in plan.steps:
            if step.tool and step.tool not in tools_used:
                tools_used.append(step.tool)

        # Surface document chunks returned by backend tools as citations.
        sources = []
        for item in results:
            if item.get("tool") == "document_search":
                value = item.get("result")
                if isinstance(value, list):
                    sources.extend(value)

        return AgentRunResult(
            contract_version=request.contract_version,
            run_id=request.run_id,
            status="completed",
            answer=answer,
            plan_summary=plan_summary,
            tools_used=tools_used,
            sources=sources,
        )
    except Exception as e:
        return AgentRunResult(
            contract_version=request.contract_version,
            run_id=request.run_id,
            status="failed",
            error_message=str(e),
        )
