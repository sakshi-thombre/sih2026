"""Tests for the CORS configuration in app/main.py.

Origins come from settings.cors_allow_origins (FRONTEND_ORIGINS in
.env) — these tests exercise the default value
("http://localhost:3000,http://localhost:5173" from
app/core/config.py), since CORSMiddleware is added once at app
creation and isn't a per-request dependency that can be overridden.
"""

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app

client = TestClient(app)


def test_configured_origins_include_localhost_defaults() -> None:
    """The setting itself, not just the middleware behavior — pins down
    that local frontend dev ports work out of the box."""
    assert "http://localhost:3000" in settings.cors_allow_origins
    assert "http://localhost:5173" in settings.cors_allow_origins


def test_cors_does_not_allow_wildcard_origin() -> None:
    """Credentials (the Supabase JWT) are sent with requests, so a
    wildcard origin must never be configured — see app/main.py."""
    assert "*" not in settings.cors_allow_origins


def test_simple_request_from_allowed_origin_gets_cors_header() -> None:
    response = client.get("/api/v1/health", headers={"Origin": "http://localhost:3000"})

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_simple_request_from_disallowed_origin_gets_no_cors_header() -> None:
    response = client.get("/api/v1/health", headers={"Origin": "http://evil.example.com"})

    assert response.status_code == 200  # request still succeeds; the browser enforces CORS, not the server
    assert "access-control-allow-origin" not in response.headers


def test_preflight_request_allows_configured_origin_and_credentials() -> None:
    response = client.options(
        "/api/v1/agent/runs",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_preflight_request_from_disallowed_origin_is_rejected() -> None:
    response = client.options(
        "/api/v1/agent/runs",
        headers={
            "Origin": "http://evil.example.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )

    # Starlette's CORSMiddleware returns 400 for a preflight whose
    # origin isn't in the allow-list, without forwarding to the route.
    assert response.status_code == 400
