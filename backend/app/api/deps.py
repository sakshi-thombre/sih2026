"""Shared FastAPI dependencies.

`get_current_user` is a placeholder. Person D owns authentication —
once they implement it, this function should be replaced with real
token/session verification. Every endpoint that needs an authenticated
user should depend on this function (or `require_role` in
`app.security.permissions`) rather than reading headers directly, so
there is exactly one place to wire in the real implementation.

`get_llm_provider` is the single wiring point between the API layer
and whichever LLMProvider is configured.
"""

import secrets
from functools import lru_cache

from fastapi import Header

from app.clients.agent_client import AgentClient, HttpAgentClient
from app.core.config import Settings, settings
from app.core.exceptions import PermissionDeniedError
from app.llm.base import LLMProvider
from app.llm.ollama import OllamaProvider
from app.rag.embeddings import EmbeddingProvider, OllamaEmbeddingProvider
from app.rag.retriever import VectorStoreRetriever
from app.rag.vector_store import LocalVectorStore, VectorStore
from app.runs.store import ActionStore, InMemoryActionStore, InMemoryRunStore, RunStore
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


def get_current_user() -> dict[str, str]:
    """Placeholder for authentication.

    Person D will replace this with real auth (e.g. verifying a JWT or
    Supabase session and loading the user + role from the database).
    """
    raise NotImplementedError("Authentication is not yet implemented")


@lru_cache
def get_agent_client() -> AgentClient:
    """Returns the configured client for Person C's agent service.
    Cached as a singleton, same pattern as `get_llm_provider`."""
    return HttpAgentClient(
        base_url=settings.agent_service_base_url,
        timeout_seconds=settings.agent_service_timeout_seconds,
    )


@lru_cache
def get_run_store() -> RunStore:
    """In-memory prototype store for agent runs (Phase 4). Person D can
    swap this for a PostgreSQL-backed `RunStore` later — routes and
    services depend only on the `RunStore` interface."""
    return InMemoryRunStore()


@lru_cache
def get_action_store() -> ActionStore:
    """In-memory prototype store for run action/audit records, backing
    GET /api/v1/agent/runs/{run_id}/actions."""
    return InMemoryActionStore()


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
