import logging

from fastapi.testclient import TestClient

from app.core.exceptions import AppError, NotFoundError, PermissionDeniedError
from app.core.logging import JSONFormatter
from app.main import app

client = TestClient(app, raise_server_exceptions=False)


def test_json_formatter_produces_valid_json() -> None:
    import json

    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname=__file__, lineno=1,
        msg="hello", args=(), exc_info=None,
    )
    formatted = JSONFormatter().format(record)
    parsed = json.loads(formatted)
    assert parsed["message"] == "hello"
    assert parsed["level"] == "INFO"


def test_not_found_error_maps_to_404() -> None:
    @app.get("/__test_not_found")
    def _raise_not_found() -> None:
        raise NotFoundError("thing missing")

    response = client.get("/__test_not_found")
    assert response.status_code == 404
    assert response.json() == {"error": {"code": "not_found", "message": "thing missing"}}


def test_permission_denied_maps_to_403() -> None:
    @app.get("/__test_permission_denied")
    def _raise_permission_denied() -> None:
        raise PermissionDeniedError("nope")

    response = client.get("/__test_permission_denied")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"


def test_validation_error_returns_422() -> None:
    @app.post("/__test_validation")
    def _validated(value: int) -> dict[str, int]:
        return {"value": value}

    response = client.post("/__test_validation", json={})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_unhandled_error_returns_500_without_leaking_details() -> None:
    @app.get("/__test_unhandled")
    def _raise_unhandled() -> None:
        raise ValueError("some internal secret detail")

    response = client.get("/__test_unhandled")
    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "internal_error"
    assert "secret" not in body["error"]["message"]


def test_app_error_base_defaults_to_500() -> None:
    class CustomError(AppError):
        pass

    @app.get("/__test_custom_error")
    def _raise_custom() -> None:
        raise CustomError("custom failure")

    response = client.get("/__test_custom_error")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
