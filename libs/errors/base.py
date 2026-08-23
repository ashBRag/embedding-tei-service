"""Reusable API error hierarchy + FastAPI exception handlers.

Gives every error response - expected (404, 409, ...) or unexpected (bugs,
DB outages) - the same JSON shape:

    {"error": {"code": "not_found", "message": "...", "details": {...}}}

Self-contained: takes a logger-like object as a parameter instead of
importing libs.logging, so it stays independently reusable/extractable.

Usage in a project's own main.py:

    from libs.errors import AppError, NotFoundError, register_exception_handlers

    register_exception_handlers(app, logger=logger, debug=settings.DEBUG)

    @app.get("/widgets/{id}")
    async def get_widget(id: int):
        widget = await find_widget(id)
        if widget is None:
            raise NotFoundError(f"Widget {id} not found")
        return widget
"""

from typing import Any, Protocol

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException


class _Logger(Protocol):
    """Structural type for whatever logger register_exception_handlers() is given."""

    def error(self, event: str, **kwargs: Any) -> None: ...


class AppError(Exception):
    """Base class for all expected/handled API errors.

    Raise a subclass (or this directly) from route/service code; the
    registered handler turns it into a consistent JSON error response.
    """

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    code: str = "internal_error"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None):
        """Store the human-readable message and optional structured details."""
        super().__init__(message)
        self.message = message
        self.details = details or {}


class BadRequestError(AppError):
    """The request itself is malformed/invalid in a way validation didn't catch."""

    status_code = status.HTTP_400_BAD_REQUEST
    code = "bad_request"


class UnauthorizedError(AppError):
    """No valid credentials were supplied."""

    status_code = status.HTTP_401_UNAUTHORIZED
    code = "unauthorized"


class ForbiddenError(AppError):
    """Credentials were valid but don't grant access to this resource."""

    status_code = status.HTTP_403_FORBIDDEN
    code = "forbidden"


class NotFoundError(AppError):
    """The requested resource doesn't exist."""

    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"


class ConflictError(AppError):
    """The request conflicts with the current state (e.g. duplicate, stale update)."""

    status_code = status.HTTP_409_CONFLICT
    code = "conflict"


def _error_response(status_code: int, code: str, message: str, details: dict[str, Any] | None = None) -> JSONResponse:
    """Build the one consistent error body shape used by every handler below."""
    body: dict[str, Any] = {"error": {"code": code, "message": message}}
    if details:
        body["error"]["details"] = details
    return JSONResponse(status_code=status_code, content=body)


def register_exception_handlers(app: FastAPI, logger: _Logger, debug: bool = False) -> None:
    """Attach handlers for AppError, HTTPException, validation errors, and any other Exception.

    Args:
        app: The FastAPI app to attach handlers to.
        logger: Used to log every error with request path/method context.
        debug: When True, unhandled exceptions include the exception message
            in the response; when False (production), the response only ever
            says "internal_server_error" so internals never leak to clients.
    """

    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        """Expected, application-raised errors (404, 409, ...) - always safe to expose."""
        logger.error(
            "app_error",
            code=exc.code,
            message=exc.message,
            path=request.url.path,
            method=request.method,
        )
        return _error_response(exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(HTTPException)
    async def handle_http_exception(request: Request, exc: HTTPException) -> JSONResponse:
        """Handle Starlette/FastAPI's HTTPException.

        Registered on the Starlette base class (not FastAPI's subclass) so it
        also catches routing-layer 404/405 responses, not just explicit
        `raise HTTPException(...)` from route/dependency code.
        """
        logger.error(
            "http_exception",
            status_code=exc.status_code,
            detail=exc.detail,
            path=request.url.path,
            method=request.method,
        )
        return _error_response(exc.status_code, "http_error", str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        """Pydantic/FastAPI request validation failures, reshaped to the common error format."""
        logger.error(
            "validation_error",
            path=request.url.path,
            method=request.method,
            errors=str(exc.errors()),
        )
        # exc.errors()[i]["loc"] starts with "body"/"query"/etc; keep it out of
        # the field path since API consumers only care about the field name.
        field_errors = [
            {
                "field": " -> ".join(str(part) for part in error["loc"] if part != "body"),
                "message": error["msg"],
            }
            for error in exc.errors()
        ]
        return _error_response(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "validation_error",
            "Request validation failed",
            details={"errors": field_errors},
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        """Last-resort catch-all for bugs/unhandled exceptions.

        Always logs the real exception; only echoes it back to the client
        when debug=True, so production responses never leak internals.
        """
        logger.error(
            "unhandled_exception",
            exception=repr(exc),
            path=request.url.path,
            method=request.method,
        )
        message = str(exc) if debug else "An unexpected error occurred"
        return _error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "internal_error", message)
