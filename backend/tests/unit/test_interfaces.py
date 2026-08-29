"""Smoke tests for the Phase 1 interface scaffolding.

These confirm the abstractions are wired correctly (importable,
enforce their contracts) without needing a real database, LLM, or
vector store.
"""

import pytest

from app.audit.logger import AuditEvent, log_event
from app.llm.base import LLMProvider
from app.rag.base import DocumentChunk, Retriever
from app.tools.base import Tool, ToolRegistry, ToolResult


def test_llm_provider_cannot_be_instantiated_directly() -> None:
    with pytest.raises(TypeError):
        LLMProvider()  # type: ignore[abstract]


def test_retriever_cannot_be_instantiated_directly() -> None:
    with pytest.raises(TypeError):
        Retriever()  # type: ignore[abstract]


def test_document_chunk_schema_holds_citation_fields() -> None:
    chunk = DocumentChunk(
        document_id="doc-1",
        filename="sop.pdf",
        chunk_id="chunk-1",
        text="Some safety procedure text",
        score=0.87,
        page_number=3,
    )
    assert chunk.page_number == 3


def test_tool_registry_register_and_lookup() -> None:
    class DummyTool(Tool):
        name = "dummy_tool"
        description = "does nothing"
        input_schema = None  # type: ignore[assignment]

        async def run(self, input_data: object) -> ToolResult:
            return ToolResult(success=True, data={"ok": True})

    registry = ToolRegistry()
    registry.register(DummyTool())

    assert "dummy_tool" in registry.list_tools()
    assert registry.get("dummy_tool") is not None
    assert registry.get("unknown_tool") is None


def test_audit_log_event_does_not_raise() -> None:
    log_event(AuditEvent(event_type="test_event", run_id="run-1", user_id="user-1"))
