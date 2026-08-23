"""Structured logging setup (structlog) with dual console/JSON output.

Generic and reusable: `setup_logging(settings)` takes any settings object
that exposes DEBUG, LOG_DIR, LOG_FORMAT and an ENVIRONMENT with a `.value`
(e.g. `libs.config.BaseAppSettings`).

Also provides request-scoped context binding (`bind_context`/`clear_context`)
so middleware can attach fields like `session_id`/`user_id` that get merged
into every log line emitted during that request, without threading them
through every function call.
"""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

import structlog


class _LoggingSettings(Protocol):
    """Structural type for whatever settings object setup_logging() is given."""

    DEBUG: bool
    LOG_DIR: Path
    LOG_LEVEL: str
    LOG_FORMAT: str
    ENVIRONMENT: Any  # anything with a `.value` str, e.g. an Environment enum


# Holds per-request fields (session_id, user_id, ...) so every log call
# during that request automatically includes them without passing them around.
_request_context: ContextVar[dict[str, Any] | None] = ContextVar("request_context", default=None)


def bind_context(**kwargs: Any) -> None:
    """Merge key-value pairs into the current request's logging context."""
    current = _request_context.get() or {}
    _request_context.set({**current, **kwargs})


def clear_context() -> None:
    """Reset the logging context (call at the start/end of each request)."""
    _request_context.set({})


def get_context() -> dict[str, Any]:
    """Return the current request's logging context."""
    return _request_context.get() or {}


def _add_context_to_event_dict(logger: Any, method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """Structlog processor: merge the request-scoped context into each event."""
    event_dict.update(get_context())
    return event_dict


class JsonlFileHandler(logging.Handler):
    """Appends one JSON object per log line to a daily rotating file.

    Rotation is by filename (one file per day per environment), not by size,
    so it's simple and dependency-free rather than using RotatingFileHandler.
    """

    def __init__(self, file_path: Path):
        """Store the target file path; the file is opened fresh on each emit()."""
        super().__init__()
        self.file_path = file_path

    def emit(self, record: logging.LogRecord) -> None:
        """Write the record as one JSON line; failures go through handleError."""
        try:
            log_entry = {
                "timestamp": datetime.fromtimestamp(record.created).isoformat(),
                "level": record.levelname,
                "message": record.getMessage(),
                "module": record.module,
                "function": record.funcName,
                "filename": record.pathname,
                "line": record.lineno,
            }
            if hasattr(record, "extra"):
                log_entry.update(record.extra)

            with open(self.file_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry) + "\n")
        except Exception:
            self.handleError(record)


def _log_file_path(settings: _LoggingSettings) -> Path:
    env_prefix = settings.ENVIRONMENT.value
    return settings.LOG_DIR / f"{env_prefix}-{datetime.now().strftime('%Y-%m-%d')}.jsonl"


def _build_processors(include_file_info: bool) -> list[Any]:
    """Shared structlog processor chain, before the final renderer is appended."""
    processors: list[Any] = [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        _add_context_to_event_dict,
    ]

    # Callsite info (file/line/func) is useful in dev but noisy/expensive in prod logs.
    if include_file_info:
        processors.append(
            structlog.processors.CallsiteParameterAdder(
                {
                    structlog.processors.CallsiteParameter.FILENAME,
                    structlog.processors.CallsiteParameter.FUNC_NAME,
                    structlog.processors.CallsiteParameter.LINENO,
                    structlog.processors.CallsiteParameter.MODULE,
                }
            )
        )

    return processors


def setup_logging(settings: _LoggingSettings, extra_context: dict[str, Any] | None = None) -> structlog.BoundLogger:
    """Configure stdlib logging + structlog and return a ready-to-use logger.

    Args:
        settings: object with DEBUG, LOG_DIR, LOG_LEVEL, LOG_FORMAT, ENVIRONMENT.
        extra_context: static fields to stamp onto every log line (e.g. environment name).

    Returns:
        A structlog logger instance (call `.info(...)`, `.error(...)`, etc).
    """
    settings.LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_level = logging.DEBUG if settings.DEBUG else logging.INFO

    file_handler = JsonlFileHandler(_log_file_path(settings))
    file_handler.setLevel(log_level)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)

    # Only show detailed callsite info in console mode (dev/test), not JSON (staging/prod).
    processors = _build_processors(include_file_info=settings.LOG_FORMAT == "console")

    if extra_context:
        processors.append(lambda _, __, event_dict: {**event_dict, **extra_context})

    logging.basicConfig(
        format="%(message)s",
        level=log_level,
        handlers=[file_handler, console_handler],
        force=True,  # re-configuring is safe if setup_logging() is called more than once (e.g. in tests)
    )

    renderer = (
        structlog.dev.ConsoleRenderer() if settings.LOG_FORMAT == "console" else structlog.processors.JSONRenderer()
    )

    structlog.configure(
        processors=[*processors, renderer],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    return structlog.get_logger()
