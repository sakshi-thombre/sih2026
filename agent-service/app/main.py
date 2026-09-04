from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

from app.agent import Agent


app = FastAPI(
    title="Sovereign Agent Service",
    description="On-premise Agentic AI Service",
    version="1.0.0"
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


@app.get("/")
async def root():
    return {
        "status": "Agent Service is running"
    }


@app.post("/agent/run", response_model=AgentRunResult)
async def run_agent(request: AgentRunRequest):

    try:
        plan = await agent.create_plan(request.task)

        results = await agent.execute_plan(plan)

        answer = await agent.generate_final_answer(
            request.task,
            results
        )

        plan_summary = []

        for step in plan.steps:
            if step.description:
                plan_summary.append(step.description)

        tools_used = []

        for step in plan.steps:
            if step.tool and step.tool not in tools_used:
                tools_used.append(step.tool)

        return AgentRunResult(
            contract_version=request.contract_version,
            run_id=request.run_id,
            status="completed",
            answer=answer,
            plan_summary=plan_summary,
            tools_used=tools_used,
            sources=[],
            error_message=None
        )

    except Exception as e:

        return AgentRunResult(
            contract_version=request.contract_version,
            run_id=request.run_id,
            status="failed",
            answer=None,
            plan_summary=[],
            tools_used=[],
            sources=[],
            error_message=str(e)
        )
