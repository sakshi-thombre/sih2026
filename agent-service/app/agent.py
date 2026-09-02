import json	

from app.ollama_client import OllamaClient
from app.prompts import PLANNER_PROMPT, FINAL_ANSWER_PROMPT
from app.schemas import AgentPlan
from app.tools.document_search import document_search
from app.tools.sql_query import sql_query
from app.tools.report_generator import report_generator


class Agent:

    def __init__(self):
        self.llm = OllamaClient()

    async def create_plan(self, task: str) -> AgentPlan:

        prompt = PLANNER_PROMPT.format(task=task)

        response = await self.llm.generate(prompt)

        try:
            data = json.loads(response)
            return AgentPlan(**data)

        except Exception as e:
            raise ValueError(
                f"Qwen returned an invalid plan: {response}"
            ) from e

    async def execute_plan(self, plan: AgentPlan) -> list:

        results = []

        for step in plan.steps:

            if step.tool == "document_search":

                result = document_search(
                    step.description
                )

            elif step.tool == "sql_query":

                result = sql_query(
                    step.description
                )

            elif step.tool == "report_generator":

                source_data = []

                for previous_result in results:

                    if isinstance(previous_result["result"], list):
                        source_data.extend(
                            previous_result["result"]
                        )

                result = report_generator(
                    "Agent Generated Report",
                    source_data
                )

            else:

                result = {
                    "error": f"Unknown tool: {step.tool}"
                }

            results.append({
                "step": step.step,
                "tool": step.tool,
                "description": step.description,
                "result": result
            })

        return results

    async def generate_final_answer(
        self,
        task: str,
        results: list
    ) -> str:

        prompt = FINAL_ANSWER_PROMPT.format(
            task=task,
            results=json.dumps(
                results,
                indent=2
            )
        )

        response = await self.llm.generate(prompt)

        return response
