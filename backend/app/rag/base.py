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
    page_number: int | None = None
    chunk_index: int | None = None


class Retriever(ABC):
    @abstractmethod
    async def retrieve(self, query: str, top_k: int = 5) -> list[DocumentChunk]:
        """Return the top_k most relevant chunks for a query."""
