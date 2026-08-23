"""Structured logging (structlog) with request-scoped context binding.

Self-contained: takes a settings-shaped object as a parameter rather than
importing libs.config, so it stays independently reusable/extractable.
"""

from libs.logging.base import (
    JsonlFileHandler,
    bind_context,
    clear_context,
    get_context,
    setup_logging,
)

__all__ = [
    "JsonlFileHandler",
    "bind_context",
    "clear_context",
    "get_context",
    "setup_logging",
]
