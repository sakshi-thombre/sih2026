"""Supabase access for the FastAPI backend.

Two distinct clients, deliberately kept separate:

- `get_db`: per-request, scoped to the caller's own JWT (via
  `client.postgrest.auth(token)`). Every PostgREST query made through
  it is subject to Row Level Security exactly as if the frontend had
  queried Supabase directly — this is what lets `user_profiles`,
  `agent_action_logs`, etc. enforce the engineer/manager and
  own-row/own-unit scoping already defined in
  supabase/migrations/0002_rls_policies.sql without the backend
  reimplementing it. Not cached: unlike app.api.deps's provider
  singletons, the identity differs on every request.

- `get_service_db`: a singleton authenticated with the service-role
  key, which bypasses RLS entirely. Its only sanctioned use is the one
  endpoint Person C's agent service calls
  (POST /api/v1/agent/tools/execute) where there is no end-user JWT to
  scope by — that request is authenticated via
  `app.api.deps.verify_internal_service` instead. Never wire this into
  a route the frontend calls.
"""

from functools import lru_cache

from fastapi import Depends, Header
from supabase import AsyncClient

from app.core.config import settings
from app.core.exceptions import ServiceUnavailableError, UnauthorizedError

_BEARER_PREFIX = "bearer "


def get_bearer_token(authorization: str | None = Header(default=None)) -> str:
    """Extracts the raw JWT from `Authorization: Bearer <token>`.
    Fails closed (401) if the header is missing or malformed, before
    any Supabase call is attempted."""
    if not authorization or not authorization.lower().startswith(_BEARER_PREFIX):
        raise UnauthorizedError("Missing or malformed Authorization header")
    token = authorization[len(_BEARER_PREFIX) :].strip()
    if not token:
        raise UnauthorizedError("Missing bearer token")
    return token


def get_db(token: str = Depends(get_bearer_token)) -> AsyncClient:
    """Per-request Supabase client authenticated as the calling user.
    Construction itself does no I/O (no session-restore round trip) —
    it just attaches `token` as the bearer credential PostgREST sends
    on every query issued through this client."""
    if not settings.supabase_url or not settings.supabase_anon_key:
        raise ServiceUnavailableError("Supabase is not configured (supabase_url/supabase_anon_key)")
    client = AsyncClient(settings.supabase_url, settings.supabase_anon_key)
    client.postgrest.auth(token)
    return client


@lru_cache
def get_service_db() -> AsyncClient:
    """Service-role Supabase client. See module docstring — do not use
    this for anything reachable from a normal user request."""
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise ServiceUnavailableError(
            "Supabase service-role access is not configured (supabase_url/supabase_service_role_key)"
        )
    return AsyncClient(settings.supabase_url, settings.supabase_service_role_key)
