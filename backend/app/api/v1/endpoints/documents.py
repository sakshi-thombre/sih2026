"""Document ingestion and search endpoints. Development/prototype API,
same status as app/api/v1/endpoints/llm.py — not the final agent API.

Routes stay thin: read/validate the request, delegate to
app.services.rag_service, return the response. No extraction, chunking,
embedding, or vector-search logic lives here.
"""

from fastapi import APIRouter, Depends, UploadFile

from app.api.deps import get_embedding_provider, get_settings, get_vector_store
from app.core.config import Settings
from app.core.exceptions import InvalidDocumentError
from app.rag.embeddings import EmbeddingProvider
from app.rag.vector_store import VectorStore
from app.schemas.rag import SearchRequest, SearchResponse, UploadResponse
from app.services.rag_service import ingest_document, search_documents

router = APIRouter()

_UPLOAD_READ_CHUNK_BYTES = 1024 * 1024  # 1 MB


async def _read_upload(file: UploadFile, max_bytes: int) -> bytes:
    """Reads the upload in bounded chunks, aborting as soon as the size
    limit is exceeded rather than buffering an arbitrarily large file
    before checking."""
    buffer = bytearray()
    while True:
        chunk = await file.read(_UPLOAD_READ_CHUNK_BYTES)
        if not chunk:
            break
        buffer.extend(chunk)
        if len(buffer) > max_bytes:
            raise InvalidDocumentError(
                f"Uploaded file exceeds the maximum allowed size of {max_bytes} bytes"
            )
    return bytes(buffer)


@router.post("/documents/upload", response_model=UploadResponse)
async def upload_document(
    file: UploadFile,
    settings: Settings = Depends(get_settings),
    embedding_provider: EmbeddingProvider = Depends(get_embedding_provider),
    vector_store: VectorStore = Depends(get_vector_store),
) -> UploadResponse:
    if not file.filename:
        raise InvalidDocumentError("Uploaded file must have a filename")

    content = await _read_upload(file, settings.max_upload_size_bytes)

    metadata = await ingest_document(
        filename=file.filename,
        content=content,
        embedding_provider=embedding_provider,
        vector_store=vector_store,
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
    )
    return UploadResponse(document=metadata)


@router.post("/documents/search", response_model=SearchResponse)
async def search(
    request: SearchRequest,
    embedding_provider: EmbeddingProvider = Depends(get_embedding_provider),
    vector_store: VectorStore = Depends(get_vector_store),
) -> SearchResponse:
    results = await search_documents(
        query=request.query,
        top_k=request.top_k,
        embedding_provider=embedding_provider,
        vector_store=vector_store,
    )
    return SearchResponse(query=request.query, results=results)
