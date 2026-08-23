"""API error hierarchy + consistent FastAPI exception handlers.

Self-contained: no dependency on any other libs/* package.
"""

from libs.errors.base import (
    AppError,
    BadRequestError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
    register_exception_handlers,
)

__all__ = [
    "AppError",
    "BadRequestError",
    "ConflictError",
    "ForbiddenError",
    "NotFoundError",
    "UnauthorizedError",
    "register_exception_handlers",
]
