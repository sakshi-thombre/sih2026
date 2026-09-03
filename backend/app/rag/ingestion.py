"""Ingestion orchestration: extract -> chunk -> shape into DocumentChunk.

Does not embed or store — that's the caller's job (app/services/rag_service.py)
so this module stays testable without a real or mocked Ollama instance.
"""

from pathlib import Path
from uuid import uuid4

from app.core.exceptions import InvalidDocumentError
from app.rag.base import DocumentChunk
from app.rag.chunking import chunk_document
from app.rag.loaders import ExtractedDocument, load_document


class IngestedDocument:
    def __init__(self, document_id: str, filename: str, file_type: str, chunks: list[DocumentChunk]) -> None:
        self.document_id = document_id
        self.filename = filename
        self.file_type = file_type
        self.chunks = chunks


def prepare_document(
    filename: str, content: bytes, chunk_size: int, chunk_overlap: int, unit_id: str
) -> IngestedDocument:
    """Extract and chunk an uploaded file's content. Raises
    `InvalidDocumentError` for anything that can't produce usable chunks.

    `unit_id` is stamped onto every resulting chunk — the caller (see
    app.services.rag_service.ingest_document) is responsible for
    determining it from the authenticated user, never from this
    function or the raw upload."""
    extracted: ExtractedDocument = load_document(filename, content)
    chunks = chunk_document(extracted.pages, chunk_size, chunk_overlap)
    if not chunks:
        raise InvalidDocumentError("Document did not produce any usable text chunks")

    document_id = str(uuid4())
    # Never trust the caller-provided filename for anything but display —
    # strip any path components before it's persisted or returned.
    safe_filename = Path(filename).name

    document_chunks = [
        DocumentChunk(
            document_id=document_id,
            filename=safe_filename,
            chunk_id=f"{document_id}:{chunk.chunk_index}",
            text=chunk.text,
            score=0.0,
            unit_id=unit_id,
            page_number=chunk.page_number,
            chunk_index=chunk.chunk_index,
        )
        for chunk in chunks
    ]

    return IngestedDocument(
        document_id=document_id,
        filename=safe_filename,
        file_type=extracted.file_type,
        chunks=document_chunks,
    )
