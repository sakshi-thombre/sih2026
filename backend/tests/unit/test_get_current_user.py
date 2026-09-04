"""Direct unit tests for app.api.deps.get_current_user.

Every route test in this repo overrides get_current_user with a
lambda via app.dependency_overrides, so the real implementation has
no coverage anywhere else. These tests call it directly (it's a plain
async function, not a route) with a real supabase.AsyncClient wired to
httpx.MockTransport — the same mocking seam used in
tests/unit/test_supabase_store.py, extended to also cover
`db.auth.get_user`: AsyncClientOptions.httpx_client is threaded into
both the postgrest client (supabase/_async/client.py::_init_postgrest_client)
and the auth client (supabase/_async/client.py::_init_supabase_auth_client),
and supabase_auth's AsyncGoTrueBaseAPI._request ultimately calls
`self._http_client.request(method, url, ...)` — an absolute-URL httpx
call MockTransport intercepts regardless of base_url, exactly like the
postgrest request path already relied on in test_supabase_store.py.

No live Supabase project required.
"""

from typing import Any, Callable

import httpx
import pytest
from supabase import AsyncClient
from supabase.lib.client_options import AsyncClientOptions

from app.api.deps import get_current_user
from app.core.exceptions import ServiceUnavailableError, UnauthorizedError
from app.db.session import get_bearer_token

Handler = Callable[[httpx.Request], httpx.Response]


def make_db(handler: Handler) -> AsyncClient:
    transport = httpx.MockTransport(handler)
    httpx_client = httpx.AsyncClient(transport=transport)
    options = AsyncClientOptions(httpx_client=httpx_client)
    return AsyncClient("http://localhost:54321", "test-anon-key", options=options)


def user_json(user_id: str) -> dict[str, Any]:
    """Minimal valid body for supabase_auth.types.User — id, app_metadata,
    user_metadata, aud and created_at are the only required fields."""
    return {
        "id": user_id,
        "app_metadata": {},
        "user_metadata": {},
        "aud": "authenticated",
        "created_at": "2026-01-01T00:00:00Z",
    }


def routing_handler(
    *,
    auth_response: httpx.Response,
    profiles_response: httpx.Response | None = None,
    profiles_error: Exception | None = None,
) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/auth/v1/user":
            return auth_response
        if request.url.path == "/rest/v1/user_profiles":
            if profiles_error is not None:
                raise profiles_error
            assert profiles_response is not None
            return profiles_response
        raise AssertionError(f"unexpected request path: {request.url.path}")

    return handler


# ---------------------------------------------------------------------------
# Valid auth user + valid user_profiles row
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_valid_user_and_profile_returns_mapped_dict() -> None:
    db = make_db(
        routing_handler(
            auth_response=httpx.Response(200, json=user_json("user-1")),
            profiles_response=httpx.Response(
                200,
                json=[{"id": "user-1", "full_name": "Jane Engineer", "role": "engineer", "unit_id": "unit-5"}],
            ),
        )
    )

    result = await get_current_user(token="valid-jwt", db=db)

    assert result == {
        "user_id": "user-1",
        "role": "engineer",
        "unit_id": "unit-5",
        "full_name": "Jane Engineer",
    }


# ---------------------------------------------------------------------------
# role/unit/full_name mapping — None values collapse to empty strings
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_missing_unit_id_and_full_name_map_to_empty_strings() -> None:
    db = make_db(
        routing_handler(
            auth_response=httpx.Response(200, json=user_json("user-2")),
            profiles_response=httpx.Response(
                200,
                json=[{"id": "user-2", "full_name": None, "role": "manager", "unit_id": None}],
            ),
        )
    )

    result = await get_current_user(token="valid-jwt", db=db)

    assert result == {
        "user_id": "user-2",
        "role": "manager",
        "unit_id": "",
        "full_name": "",
    }


# ---------------------------------------------------------------------------
# Missing/malformed bearer token
# ---------------------------------------------------------------------------
# get_bearer_token is the dependency get_current_user uses for its `token`
# param (app/api/deps.py: `token: str = Depends(get_bearer_token)`), and it
# fails closed before any Supabase call is made — tested directly here
# since it makes no Supabase calls to mock.


def test_missing_authorization_header_raises_unauthorized() -> None:
    with pytest.raises(UnauthorizedError):
        get_bearer_token(authorization=None)


def test_malformed_authorization_header_raises_unauthorized() -> None:
    with pytest.raises(UnauthorizedError):
        get_bearer_token(authorization="NotBearer sometoken")


def test_bearer_header_with_no_token_raises_unauthorized() -> None:
    with pytest.raises(UnauthorizedError):
        get_bearer_token(authorization="Bearer   ")


# ---------------------------------------------------------------------------
# Supabase auth failure
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_auth_rejection_raises_unauthorized() -> None:
    db = make_db(
        routing_handler(
            auth_response=httpx.Response(401, json={"error_code": "bad_jwt", "msg": "invalid token"}),
        )
    )

    with pytest.raises(UnauthorizedError):
        await get_current_user(token="expired-jwt", db=db)


@pytest.mark.anyio
async def test_auth_transport_error_raises_unauthorized() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    db = make_db(handler)

    with pytest.raises(UnauthorizedError):
        await get_current_user(token="any-jwt", db=db)


# ---------------------------------------------------------------------------
# Missing user_profiles row
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_no_matching_profile_row_raises_unauthorized() -> None:
    db = make_db(
        routing_handler(
            auth_response=httpx.Response(200, json=user_json("user-3")),
            profiles_response=httpx.Response(200, json=[]),
        )
    )

    with pytest.raises(UnauthorizedError):
        await get_current_user(token="valid-jwt", db=db)


# ---------------------------------------------------------------------------
# Supabase service/unavailable error (profile lookup)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_profile_lookup_transport_error_raises_service_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/auth/v1/user":
            return httpx.Response(200, json=user_json("user-4"))
        raise httpx.ConnectError("connection refused", request=request)

    db = make_db(handler)

    with pytest.raises(ServiceUnavailableError):
        await get_current_user(token="valid-jwt", db=db)


@pytest.mark.anyio
async def test_profile_lookup_api_error_raises_service_unavailable() -> None:
    db = make_db(
        routing_handler(
            auth_response=httpx.Response(200, json=user_json("user-5")),
            profiles_response=httpx.Response(
                500,
                json={"message": "internal error", "code": "XX000", "hint": None, "details": None},
            ),
        )
    )

    with pytest.raises(ServiceUnavailableError):
        await get_current_user(token="valid-jwt", db=db)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
