"""Reusable, environment-aware settings base for pydantic-settings.

Any project can subclass `BaseAppSettings`, add its own fields, and get:
  - `.env.<environment>` / `.env.<environment>.local` / `.env` file resolution
  - Per-environment defaults (e.g. stricter rate limits + WARNING logs in prod)
    that only kick in when the corresponding env var isn't set explicitly.

Usage in a project's own `core/config.py`:

    from libs.config import BaseAppSettings, Environment

    class Settings(BaseAppSettings):
        PROJECT_NAME: str = "My Service"
        # ... project-specific fields ...

    settings = Settings().apply_environment_defaults()
"""

import os
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, ClassVar

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Environment(StrEnum):
    """The set of environments an app can run in."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TEST = "test"


def get_environment() -> Environment:
    """Read APP_ENV and map it to an Environment, defaulting to development.

    Accepts common aliases (e.g. "prod", "stage") so ops tooling doesn't have
    to match the enum spelling exactly.
    """
    match os.getenv("APP_ENV", "development").lower():
        case "production" | "prod":
            return Environment.PRODUCTION
        case "staging" | "stage":
            return Environment.STAGING
        case "test":
            return Environment.TEST
        case _:
            return Environment.DEVELOPMENT


def resolve_env_file(root_dir: Path) -> str | None:
    """Pick the most specific .env file that exists for the current environment.

    Search order (first match wins), relative to `root_dir`:
        .env.<environment>.local  ->  .env.<environment>  ->  .env.local  ->  .env

    This lets a `.local` file hold machine-specific overrides (e.g. a
    developer's own DB port) without touching the checked-in `.env.<env>`.
    """
    env = get_environment()
    candidates = [
        root_dir / f".env.{env.value}.local",
        root_dir / f".env.{env.value}",
        root_dir / ".env.local",
        root_dir / ".env",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return None


class BaseAppSettings(BaseSettings):
    """Common settings fields + environment-default machinery.

    Subclass this in each project and add project-specific fields (project
    name, feature flags, third-party API keys, etc). The per-environment
    default table (`environment_defaults`) can be overridden per subclass to
    tune values like log level or rate limits without touching this file.
    """

    # env_file is resolved relative to the current working directory, which is
    # expected to be the project root (true for `uv run uvicorn ...` / `make dev`).
    # A subclass can override model_config if it needs a different root.
    model_config = SettingsConfigDict(
        env_file=resolve_env_file(Path.cwd()),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Fields every service in this style needs ---
    DEBUG: bool = False
    # NoDecode: skip pydantic-settings' default JSON parsing for this env var,
    # so ALLOWED_ORIGINS="http://a,http://b" works instead of requiring
    # ALLOWED_ORIGINS='["http://a","http://b"]'. The _split_comma_separated
    # validator below does the actual parsing.
    ALLOWED_ORIGINS: Annotated[list[str], NoDecode] = ["*"]

    JWT_SECRET_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_DAYS: int = 30

    LOG_DIR: Path = Path("logs")
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"  # "json" (prod/staging) or "console" (dev, pretty-printed)

    RATE_LIMIT_DEFAULT: Annotated[list[str], NoDecode] = ["200 per day", "50 per hour"]

    ENVIRONMENT: Environment = get_environment()

    @field_validator("ALLOWED_ORIGINS", "RATE_LIMIT_DEFAULT", mode="before")
    @classmethod
    def _split_comma_separated(cls, value: Any) -> Any:
        """Accept a plain comma-separated env var value, not just a JSON array.

        pydantic-settings parses list[str] fields as JSON by default (e.g.
        `["a","b"]`), which is awkward to write in a .env file. This lets
        `ALLOWED_ORIGINS="http://a,http://b"` work directly - a real list
        (already parsed from JSON, or passed in code) is left untouched.
        """
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    # Per-environment overrides applied only when the field wasn't set via env var.
    # Override this in a subclass to customize without rewriting apply_environment_defaults.
    environment_defaults: ClassVar[dict[Environment, dict[str, object]]] = {
        Environment.DEVELOPMENT: {
            "DEBUG": True,
            "LOG_LEVEL": "DEBUG",
            "LOG_FORMAT": "console",
            "RATE_LIMIT_DEFAULT": ["1000 per day", "200 per hour"],
        },
        Environment.STAGING: {
            "DEBUG": False,
            "LOG_LEVEL": "INFO",
            "LOG_FORMAT": "json",
            "RATE_LIMIT_DEFAULT": ["500 per day", "100 per hour"],
        },
        Environment.PRODUCTION: {
            "DEBUG": False,
            "LOG_LEVEL": "WARNING",
            "LOG_FORMAT": "json",
            "RATE_LIMIT_DEFAULT": ["200 per day", "50 per hour"],
        },
        Environment.TEST: {
            "DEBUG": True,
            "LOG_LEVEL": "DEBUG",
            "LOG_FORMAT": "console",
            "RATE_LIMIT_DEFAULT": ["1000 per day", "1000 per hour"],
        },
    }

    def apply_environment_defaults(self) -> BaseAppSettings:
        """Fill in environment-specific defaults, but never override an explicit env var.

        Call this once right after construction:
            settings = Settings().apply_environment_defaults()
        """
        defaults = self.environment_defaults.get(self.ENVIRONMENT, {})
        for key, value in defaults.items():
            if key not in os.environ:
                setattr(self, key, value)
        return self
