"""Controlled tool interface.

The agent (Phase 5) is only ever allowed to call `Tool` subclasses
registered in a `ToolRegistry` — never arbitrary shell commands, raw
SQL, or filesystem/network access. Every tool declares its own input
schema and required role, so permission checks happen in one place
(`ToolRegistry.get`) instead of being re-implemented per tool.
"""

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel


class ToolResult(BaseModel):
    success: bool
    data: Any = None
    error: str | None = None


class Tool(ABC):
    name: str
    description: str
    input_schema: type[BaseModel]
    required_role: str | None = None

    @abstractmethod
    async def run(self, input_data: BaseModel) -> ToolResult:
        """Validate input, perform the action, and return a structured result.

        Implementations must fail safely: catch expected errors and
        return `ToolResult(success=False, error=...)` rather than
        raising, and must never include secrets in `data` or `error`.
        """


class ToolRegistry:
    """Holds the set of tools the agent is allowed to call."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        return list(self._tools.keys())
