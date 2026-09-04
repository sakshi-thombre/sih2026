"""Structured report tool.

Report generation is deterministic and contains no privileged data access.
The data passed to it comes from earlier, permission-checked tools.
"""
from typing import Any
from pydantic import BaseModel, Field
from app.tools.base import Tool, ToolResult


class ReportGeneratorInput(BaseModel):
    title: str = Field(default="Agent Generated Report", max_length=200)
    data: list[Any] = Field(default_factory=list)


class ReportGeneratorTool(Tool):
    name = "report_generator"
    description = "Build a structured report from previously collected tool results."
    input_schema = ReportGeneratorInput
    required_role = None

    async def run(self, input_data: BaseModel, *, caller: dict[str, str]) -> ToolResult:
        assert isinstance(input_data, ReportGeneratorInput)
        return ToolResult(
            success=True,
            data={
                "title": input_data.title,
                "total_records": len(input_data.data),
                "records": input_data.data,
            },
        )
