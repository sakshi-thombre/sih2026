"""Application error hierarchy and FastAPI exception handlers.

Every error the API returns has the same JSON shape:

    {"error": {"code": "not_found", "message": "..."}}

Modules that don't exist yet (llm/, rag/, tools/) can raise
`ServiceUnavailableError` or `AppError` subclasses once they're
implemented, and they'll automatically get a consistent response
without each router needing its own try/except.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class AppError(Exception):
    """Base class for application errors that map to a clean API response."""

    status_code: int = 500
    code: str = "internal_error"

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ServiceUnavailableError(AppError):
    """Raised when a dependency (Ollama, vector store, database) is unreachable."""

    status_code = 503
    code = "service_unavailable"


class PermissionDeniedError(AppError):
    """Raised when a user or tool call lacks the required permission."""

    status_code = 403
    code = "permission_denied"


class UpstreamServiceError(AppError):
    """Raised when a dependency (e.g. Ollama) responds, but with something
    malformed or unexpected — as opposed to being unreachable entirely."""

    status_code = 502
    code = "upstream_error"


class InvalidDocumentError(AppError):
    """Raised when an uploaded document is invalid: unsupported file type,
    empty, corrupt, or contains no extractable text. Never carries the
    document content itself — only a description of what was wrong."""

    status_code = 422
    code = "invalid_document"


class InvalidStateError(AppError):
    """Raised when an operation is attempted against a run/task that is
    not in a valid state for it — e.g. cancelling a run that already
    reached a terminal state."""

    status_code = 409
    code = "invalid_state"


def _error_response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        logger.warning(
            "app_error",
            extra={"path": request.url.path, "code": exc.code, "error_message": exc.message},
        )
        return _error_response(exc.status_code, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        logger.info("validation_error", extra={"path": request.url.path, "errors": exc.errors()})
        return _error_response(422, "validation_error", "Request payload failed validation")

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_error", extra={"path": request.url.path})
        return _error_response(500, "internal_error", "An unexpected error occurred")
