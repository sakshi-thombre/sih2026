"""Unit tests for Settings validation — specifically the fail-closed
INTERNAL_SERVICE_TOKEN check. Without this, an unset token silently
disables auth on POST /api/v1/agent/tools/execute (service-role
Supabase access) outside local development.
"""

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_development_environment_allows_missing_internal_service_token() -> None:
    settings = Settings(environment="development", internal_service_token=None)
    assert settings.internal_service_token is None


def test_development_environment_allows_empty_internal_service_token() -> None:
    settings = Settings(environment="development", internal_service_token="")
    assert settings.internal_service_token == ""


def test_non_development_environment_rejects_missing_internal_service_token() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Settings(environment="production", internal_service_token=None)

    assert "INTERNAL_SERVICE_TOKEN" in str(exc_info.value)


def test_non_development_environment_rejects_empty_internal_service_token() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Settings(environment="staging", internal_service_token="")

    assert "INTERNAL_SERVICE_TOKEN" in str(exc_info.value)


def test_non_development_environment_accepts_configured_internal_service_token() -> None:
    settings = Settings(environment="production", internal_service_token="a-real-secret")
    assert settings.internal_service_token == "a-real-secret"
