"""Request/response schemas for the document ingestion and search endpoints."""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.core.config import settings
from app.rag.base import DocumentChunk


class DocumentMetadata(BaseModel):
    document_id: str
    filename: str
    file_type: str
    file_size: int
    ingested_at: datetime
    chunk_count: int


class UploadResponse(BaseModel):
    status: str = "success"
    document: DocumentMetadata


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1)

    @field_validator("top_k")
    @classmethod
    def validate_top_k(cls, value: int) -> int:
        if value > settings.max_top_k:
            raise ValueError(f"top_k must not exceed {settings.max_top_k}")
        return value


class SearchResponse(BaseModel):
    query: str
    results: list[DocumentChunk]
