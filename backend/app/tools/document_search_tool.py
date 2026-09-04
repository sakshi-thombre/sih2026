"""Example concrete Tool wrapping the existing Phase 3 Retriever —
demonstrates the ToolRegistry integration point without building a
second RAG pipeline. Registered so Person C's agent service can
request document search through the permission-checked tool execution
path (see app.services.tool_execution_service) instead of ever
touching the vector store directly.
"""

from pydantic import BaseModel, Field

from app.rag.base import Retriever
from app.tools.base import Tool, ToolResult


class DocumentSearchInput(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)


class DocumentSearchTool(Tool):
    name = "document_search"
    description = "Semantic search over ingested documents. Returns cited chunks."
    input_schema = DocumentSearchInput
    required_role = None  # both engineer and manager may search documents

    def __init__(self, retriever: Retriever) -> None:
        self._retriever = retriever

    async def run(self, input_data: BaseModel, *, caller: dict[str, str]) -> ToolResult:
        """Unit isolation mirrors app.api.v1.endpoints.documents' direct
        /documents/search: managers search unfiltered, everyone else is
        confined to their own unit_id and fails safely (rather than
        falling back to unfiltered) if they don't have one. `caller`
        comes from the run's trusted record, never from `input_data` —
        `DocumentSearchInput` has no unit_id field for an agent to set in
        the first place."""
        assert isinstance(input_data, DocumentSearchInput)

        if caller.get("role") == "manager":
            unit_id: str | None = None
        else:
            unit_id = caller.get("unit_id") or ""
            if not unit_id:
                return ToolResult(
                    success=False,
                    error="No unit assigned to this account; document search is unavailable",
                )

        try:
            chunks = await self._retriever.retrieve(input_data.query, input_data.top_k, unit_id=unit_id)
        except ValueError as exc:
            return ToolResult(success=False, error=str(exc))
        except Exception:
            return ToolResult(success=False, error="Document search is currently unavailable")

        return ToolResult(success=True, data=[chunk.model_dump(mode="json") for chunk in chunks])
