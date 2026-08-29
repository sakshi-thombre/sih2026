"""Unit tests for verify_internal_service — the service-to-service
auth placeholder guarding POST /api/v1/agent/tools/execute."""

import pytest

from app.api import deps
from app.core.exceptions import PermissionDeniedError


def test_passes_through_when_no_token_configured() -> None:
    original = deps.settings.internal_service_token
    deps.settings.internal_service_token = None
    try:
        deps.verify_internal_service(x_internal_service_token=None)  # should not raise
    finally:
        deps.settings.internal_service_token = original


def test_rejects_missing_header_when_token_configured() -> None:
    original = deps.settings.internal_service_token
    deps.settings.internal_service_token = "expected-secret"
    try:
        with pytest.raises(PermissionDeniedError):
            deps.verify_internal_service(x_internal_service_token=None)
    finally:
        deps.settings.internal_service_token = original


def test_rejects_wrong_header_when_token_configured() -> None:
    original = deps.settings.internal_service_token
    deps.settings.internal_service_token = "expected-secret"
    try:
        with pytest.raises(PermissionDeniedError):
            deps.verify_internal_service(x_internal_service_token="wrong-value")
    finally:
        deps.settings.internal_service_token = original


def test_accepts_matching_header_when_token_configured() -> None:
    original = deps.settings.internal_service_token
    deps.settings.internal_service_token = "expected-secret"
    try:
        deps.verify_internal_service(x_internal_service_token="expected-secret")  # should not raise
    finally:
        deps.settings.internal_service_token = original
