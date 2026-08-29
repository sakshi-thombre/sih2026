"""Service layer for document ingestion and retrieval.

Routes call this instead of talking to the embedding provider or
vector store directly, keeping provider/storage concerns out of
`api/` — mirrors the pattern in `app/services/llm_service.py`.

Audit events record what happened (document/chunk counts, ids) but
never document content, chunk text, embeddings, or query text.
"""

import logging
from datetime import datetime, timezone

from app.audit.logger import AuditEvent, log_event
from app.core.exceptions import ServiceUnavailableError
from app.rag.base import DocumentChunk
from app.rag.embeddings import EmbeddingProvider
from app.rag.ingestion import prepare_document
from app.rag.vector_store import VectorStore
from app.schemas.rag import DocumentMetadata

logger = logging.getLogger(__name__)


async def ingest_document(
    *,
    filename: str,
    content: bytes,
    embedding_provider: EmbeddingProvider,
    vector_store: VectorStore,
    chunk_size: int,
    chunk_overlap: int,
) -> DocumentMetadata:
    ingested = prepare_document(filename, content, chunk_size, chunk_overlap)

    texts = [chunk.text for chunk in ingested.chunks]
    embeddings = await embedding_provider.embed(texts)

    try:
        vector_store.add(ingested.chunks, embeddings)
    except ServiceUnavailableError:
        raise
    except Exception as exc:
        logger.warning("vector_store_add_failed", extra={"document_id": ingested.document_id})
        raise ServiceUnavailableError("Local vector store is unavailable") from exc

    log_event(
        AuditEvent(
            event_type="document_ingested",
            metadata={
                "document_id": ingested.document_id,
                "filename": ingested.filename,
                "file_type": ingested.file_type,
                "chunk_count": len(ingested.chunks),
            },
        )
    )

    return DocumentMetadata(
        document_id=ingested.document_id,
        filename=ingested.filename,
        file_type=ingested.file_type,
        file_size=len(content),
        ingested_at=datetime.now(timezone.utc),
        chunk_count=len(ingested.chunks),
    )


async def search_documents(
    *,
    query: str,
    top_k: int,
    embedding_provider: EmbeddingProvider,
    vector_store: VectorStore,
) -> list[DocumentChunk]:
    embeddings = await embedding_provider.embed([query])
    query_embedding = embeddings[0]

    try:
        results = vector_store.search(query_embedding, top_k)
    except ServiceUnavailableError:
        raise
    except Exception as exc:
        logger.warning("vector_store_search_failed")
        raise ServiceUnavailableError("Local vector store is unavailable") from exc

    log_event(
        AuditEvent(
            event_type="document_search",
            metadata={"top_k": top_k, "result_count": len(results)},
        )
    )

    return results
