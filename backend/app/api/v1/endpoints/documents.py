"""Document ingestion and search endpoints. Development/prototype API,
same status as app/api/v1/endpoints/llm.py — not the final agent API.

Requires an authenticated caller (see `get_current_user` in
app.api.deps) — same Supabase-JWT dependency the /agent routes use, no
second auth system.

Routes stay thin: read/validate the request, delegate to
app.services.rag_service, return the response. No extraction, chunking,
embedding, or vector-search logic lives here — except resolving which
unit_id a request is scoped to, which belongs here because it depends
on the authenticated caller's role, not on RAG internals.

Unit isolation (engineers confined to their own unit; managers not):
the authenticated user's `unit_id` from `get_current_user` is always
authoritative. An engineer-supplied `unit_id` that disagrees with their
own is rejected, never silently overridden and never trusted. See
`_resolve_upload_unit_id`/`_resolve_search_unit_id`.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Form, UploadFile

from app.api.deps import get_current_user, get_embedding_provider, get_settings, get_vector_store
from app.core.config import Settings
from app.core.exceptions import InvalidDocumentError, PermissionDeniedError
from app.rag.embeddings import EmbeddingProvider
from app.rag.vector_store import VectorStore
from app.schemas.rag import SearchRequest, SearchResponse, UploadResponse
from app.services.rag_service import ingest_document, search_documents

router = APIRouter()

_UPLOAD_READ_CHUNK_BYTES = 1024 * 1024  # 1 MB


def _is_valid_unit_id(value: str) -> bool:
    """unit_id values are Supabase `units.id`, a uuid column (see
    supabase/migrations/0001_schema.sql) — format-validating a
    manager-supplied target catches garbage input before it's stamped
    onto stored chunks."""
    try:
        UUID(value)
        return True
    except ValueError:
        return False


def _resolve_upload_unit_id(user: dict[str, str], requested_unit_id: str | None) -> str:
    """Engineers are always scoped to their own authenticated unit_id —
    a differing client-supplied unit_id is rejected outright rather
    than silently overridden, so an attempted cross-unit upload
    surfaces as an error instead of failing silently. Managers have no
    single "home unit" to default to, so they must name a target
    explicitly."""
    role = user.get("role")

    if role == "engineer":
        own_unit_id = user.get("unit_id") or ""
        if not own_unit_id:
            raise PermissionDeniedError(
                "Your account has no assigned unit; contact an administrator before uploading documents"
            )
        if requested_unit_id and requested_unit_id != own_unit_id:
            raise PermissionDeniedError("Engineers may only upload documents to their own unit")
        return own_unit_id

    if role == "manager":
        if not requested_unit_id or not requested_unit_id.strip():
            raise InvalidDocumentError("Managers must specify a target unit_id when uploading a document")
        if not _is_valid_unit_id(requested_unit_id):
            raise InvalidDocumentError("unit_id must be a valid unit identifier")
        return requested_unit_id

    raise PermissionDeniedError(f"Unsupported role '{role}' for document upload")


def _resolve_search_unit_id(user: dict[str, str]) -> str | None:
    """Engineers only ever search their own unit's documents; managers
    search across all units, so no filter (None) is applied for them."""
    role = user.get("role")

    if role == "engineer":
        own_unit_id = user.get("unit_id") or ""
        if not own_unit_id:
            raise PermissionDeniedError(
                "Your account has no assigned unit; contact an administrator before searching documents"
            )
        return own_unit_id

    if role == "manager":
        return None

    raise PermissionDeniedError(f"Unsupported role '{role}' for document search")


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
    unit_id: str | None = Form(default=None),
    user: dict[str, str] = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    embedding_provider: EmbeddingProvider = Depends(get_embedding_provider),
    vector_store: VectorStore = Depends(get_vector_store),
) -> UploadResponse:
    if not file.filename:
        raise InvalidDocumentError("Uploaded file must have a filename")

    target_unit_id = _resolve_upload_unit_id(user, unit_id)
    content = await _read_upload(file, settings.max_upload_size_bytes)

    metadata = await ingest_document(
        filename=file.filename,
        content=content,
        unit_id=target_unit_id,
        embedding_provider=embedding_provider,
        vector_store=vector_store,
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
    )
    return UploadResponse(document=metadata)


@router.post("/documents/search", response_model=SearchResponse)
async def search(
    request: SearchRequest,
    user: dict[str, str] = Depends(get_current_user),
    embedding_provider: EmbeddingProvider = Depends(get_embedding_provider),
    vector_store: VectorStore = Depends(get_vector_store),
) -> SearchResponse:
    filter_unit_id = _resolve_search_unit_id(user)
    results = await search_documents(
        query=request.query,
        top_k=request.top_k,
        unit_id=filter_unit_id,
        embedding_provider=embedding_provider,
        vector_store=vector_store,
    )
    return SearchResponse(query=request.query, results=results)
