"""RAG (retrieval) interface.

`DocumentChunk` is the shape every retrieval result must have, so
the agent layer can always cite a source regardless of which vector
store backs the retriever. `Retriever` is implemented in Phase 4
once ingestion, chunking, and embeddings exist.
"""

from abc import ABC, abstractmethod

from pydantic import BaseModel


class DocumentChunk(BaseModel):
    document_id: str
    filename: str
    chunk_id: str
    text: str
    score: float
    # Optional (rather than required) because DocumentChunk is also reused
    # as AgentRun's citation shape (see app.runs.models/supabase_store),
    # which predates unit isolation and carries no unit_id. Ingestion and
    # search (app/services/rag_service.py) always set a real value here.
    unit_id: str | None = None
    page_number: int | None = None
    chunk_index: int | None = None


class Retriever(ABC):
    @abstractmethod
    async def retrieve(self, query: str, top_k: int = 5, unit_id: str | None = None) -> list[DocumentChunk]:
        """Return the top_k most relevant chunks for a query. If unit_id is
        given, only chunks belonging to that unit are considered."""
