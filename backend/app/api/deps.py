"""Shared FastAPI dependencies.

`get_current_user` validates the caller's Supabase JWT (via
`db.auth.get_user`, i.e. Supabase's own Auth server — no local JWT
secret/JWKS handling here) and loads their role/unit from
`user_profiles`. Every endpoint that needs an authenticated user
should depend on this function (or `require_role` in
`app.security.permissions`) rather than reading headers directly, so
there is exactly one place authentication is wired in.

`get_llm_provider` is the single wiring point between the API layer
and whichever LLMProvider is configured.
"""

import secrets
from functools import lru_cache

from fastapi import Depends, Header
from supabase import AsyncClient

from app.clients.agent_client import AgentClient, HttpAgentClient
from app.core.config import Settings, settings
from app.core.exceptions import PermissionDeniedError, ServiceUnavailableError, UnauthorizedError
from app.db.session import get_bearer_token, get_db, get_service_db
from app.llm.base import LLMProvider
from app.llm.ollama import OllamaProvider
from app.rag.embeddings import EmbeddingProvider, OllamaEmbeddingProvider
from app.rag.retriever import VectorStoreRetriever
from app.rag.vector_store import LocalVectorStore, VectorStore
from app.runs.store import ActionStore, RunStore
from app.runs.supabase_store import SupabaseActionStore, SupabaseRunStore
from app.tools.base import ToolRegistry
from app.tools.document_search_tool import DocumentSearchTool


def get_settings() -> Settings:
    return settings


@lru_cache
def get_llm_provider() -> LLMProvider:
    """Returns the configured LLM provider.

    Cached as a singleton so repeated requests reuse the same provider
    instance. To use a different local model/runtime later, change
    this function — routes and services depend only on `LLMProvider`.
    """
    return OllamaProvider(
        base_url=settings.ollama_base_url,
        model=settings.ollama_model,
        timeout_seconds=settings.ollama_timeout_seconds,
    )


@lru_cache
def get_embedding_provider() -> EmbeddingProvider:
    """Returns the configured local embedding provider. Singleton for the
    same reason as `get_llm_provider`."""
    return OllamaEmbeddingProvider(
        base_url=settings.ollama_base_url,
        model=settings.embedding_model,
        timeout_seconds=settings.ollama_timeout_seconds,
        batch_size=settings.embedding_batch_size,
    )


@lru_cache
def get_vector_store() -> VectorStore:
    """Returns the configured vector store.

    Cached as a singleton so the in-memory index built from disk on
    first use is reused across requests. Person D can swap this for a
    PostgreSQL/pgvector-backed `VectorStore` implementation by changing
    only this function — routes and services depend only on the
    `VectorStore` interface.
    """
    return LocalVectorStore(settings.vector_store_path)


async def get_current_user(
    token: str = Depends(get_bearer_token),
    db: AsyncClient = Depends(get_db),
) -> dict[str, str]:
    """Validates the bearer token against Supabase Auth and loads the
    caller's role/unit from `user_profiles`. Deliberately does not
    decode/verify the JWT locally — `db.auth.get_user` asks Supabase's
    own Auth server to do that, so this works regardless of whether
    the project signs tokens with a shared secret or asymmetric keys,
    and there's no JWT secret to manage/rotate here.

    The `user_profiles` lookup goes through `db`, which is already
    scoped to `token` (see `get_db`), so it is itself subject to the
    `profiles_select` RLS policy — a user can only ever load their own
    profile this way, never impersonate another `user_id`.
    """
    try:
        auth_response = await db.auth.get_user(token)
    except Exception as exc:
        raise UnauthorizedError("Invalid or expired authentication token") from exc

    user = auth_response.user if auth_response is not None else None
    if user is None:
        raise UnauthorizedError("Invalid or expired authentication token")

    try:
        profile_response = await (
            db.table("user_profiles")
            .select("id, full_name, role, unit_id")
            .eq("id", user.id)
            .maybe_single()
            .execute()
        )
    except Exception as exc:
        raise ServiceUnavailableError("Could not load user profile from Supabase") from exc

    profile = profile_response.data if profile_response is not None else None
    if profile is None:
        raise UnauthorizedError("No user profile exists for this account")

    return {
        "user_id": profile["id"],
        "role": profile["role"],
        "unit_id": profile.get("unit_id") or "",
        "full_name": profile.get("full_name") or "",
    }


@lru_cache
def get_agent_client() -> AgentClient:
    """Returns the configured client for Person C's agent service.
    Cached as a singleton, same pattern as `get_llm_provider`."""
    return HttpAgentClient(
        base_url=settings.agent_service_base_url,
        timeout_seconds=settings.agent_service_timeout_seconds,
    )


def get_run_store(db: AsyncClient = Depends(get_db)) -> RunStore:
    """Supabase-backed store for agent runs, scoped to the calling
    user's own JWT so the `agent_action_logs` RLS policies (own row, or
    manager) enforce who can read/update which run. Not cached — unlike
    `get_llm_provider`, `db` differs per request/per user."""
    return SupabaseRunStore(db)


def get_action_store(db: AsyncClient = Depends(get_db)) -> ActionStore:
    """Supabase-backed store for run action/audit records, backing
    GET /api/v1/agent/runs/{run_id}/actions. Same per-request, user-
    scoped client as `get_run_store`."""
    return SupabaseActionStore(db)


def get_service_run_store(db: AsyncClient = Depends(get_service_db)) -> RunStore:
    """For POST /api/v1/agent/tools/execute only, which is
    authenticated as Person C's service via `verify_internal_service`
    rather than an end user — there is no user JWT to scope Supabase
    queries by, so this uses the service-role client instead. Must
    never be depended on by a route the frontend calls."""
    return SupabaseRunStore(db)


def get_service_action_store(db: AsyncClient = Depends(get_service_db)) -> ActionStore:
    """Service-role counterpart to `get_action_store` — see
    `get_service_run_store`."""
    return SupabaseActionStore(db)


@lru_cache
def get_tool_registry() -> ToolRegistry:
    """Returns the registry of tools Person C's agent service may
    request execution of via POST /api/v1/agent/tools/execute. Adding a
    new tool means registering it here — nowhere else."""
    registry = ToolRegistry()
    retriever = VectorStoreRetriever(get_vector_store(), get_embedding_provider())
    registry.register(DocumentSearchTool(retriever))
    return registry


def verify_internal_service(x_internal_service_token: str | None = Header(default=None)) -> None:
    """Service-to-service authentication boundary for endpoints called
    by Person C's agent service rather than the frontend (currently
    just POST /api/v1/agent/tools/execute).

    Placeholder, not a full auth system — Person D owns that. If
    `settings.internal_service_token` is configured, callers must
    present a matching `X-Internal-Service-Token` header or the
    request is rejected. If unset (the default), the check is a no-op
    so local development/testing needs no extra setup. Keeping this as
    a dependency (rather than nothing at all) means a real mechanism
    can be dropped in later without redesigning the endpoint.
    """
    if settings.internal_service_token is not None:
        if x_internal_service_token is None or not secrets.compare_digest(
            x_internal_service_token, settings.internal_service_token
        ):
            raise PermissionDeniedError("Invalid or missing internal service token")
