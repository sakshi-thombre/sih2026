import json
from typing import Any

from app.backend_client import BackendToolClient
from app.ollama_client import OllamaClient
from app.prompts import PLANNER_PROMPT, FINAL_ANSWER_PROMPT
from app.schemas import AgentPlan


class Agent:
    """Reasoning/orchestration layer.

    Tool execution is deliberately delegated to the backend. This service
    owns planning and answer generation; the backend owns data access,
    authorization, auditing, and registered tool execution.
    """

    def __init__(self, backend_client: BackendToolClient | None = None):
        self.llm = OllamaClient()
        self.backend = backend_client or BackendToolClient()

    async def create_plan(self, task: str, context: dict[str, Any] | None = None) -> AgentPlan:
        prompt = PLANNER_PROMPT.format(
            task=task,
            context=json.dumps(context or {}, indent=2, sort_keys=True),
        )
        response = await self.llm.generate(prompt)
        try:
            data = json.loads(response)
            return AgentPlan(**data)
        except Exception as e:
            raise ValueError(f"Qwen returned an invalid plan: {response}") from e

    async def execute_plan(self, run_id: str, plan: AgentPlan) -> list:
        results = []
        for step in plan.steps:
            tool_input = {"query": step.description}
            if step.tool == "report_generator":
                source_data = []
                for previous_result in results:
                    value = previous_result.get("result", {})
                    if isinstance(value, dict):
                        value = value.get("data")
                    if isinstance(value, list):
                        source_data.extend(value)
                tool_input = {
                    "title": "Agent Generated Report",
                    "data": source_data,
                }

            response = await self.backend.execute(
                run_id=run_id,
                tool_name=step.tool,
                input_data=tool_input,
            )
            result = response.get("data") if response.get("success") else {
                "error": response.get("error") or "Tool execution failed"
            }
            results.append({
                "step": step.step,
                "tool": step.tool,
                "description": step.description,
                "result": result,
            })
        return results

    async def generate_final_answer(self, task: str, results: list) -> str:
        prompt = FINAL_ANSWER_PROMPT.format(
            task=task,
            results=json.dumps(results, indent=2),
        )
        return await self.llm.generate(prompt)
