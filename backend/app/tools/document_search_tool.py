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

    async def run(self, input_data: BaseModel) -> ToolResult:
        assert isinstance(input_data, DocumentSearchInput)
        try:
            chunks = await self._retriever.retrieve(input_data.query, input_data.top_k)
        except ValueError as exc:
            return ToolResult(success=False, error=str(exc))
        except Exception:
            return ToolResult(success=False, error="Document search is currently unavailable")

        return ToolResult(success=True, data=[chunk.model_dump(mode="json") for chunk in chunks])
