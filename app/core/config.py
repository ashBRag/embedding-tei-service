"""Project-specific application settings.

Generic env/logging/rate-limit machinery lives in libs.config;
this file only adds fields and defaults specific to *this* project.
"""

from pydantic import model_validator

from libs.config import BaseAppSettings, Environment

__all__ = ["Environment", "settings"]


class Settings(BaseAppSettings):
    """This project's settings: adds identity/API fields on top of the base."""

    PROJECT_NAME: str = "Embedding Service"
    PROJECT_SLUG: str = "embedding-service"
    VERSION: str = "1.0.0"
    DESCRIPTION: str = "An API endpoint between TEI and consuming services: batches text and returns embeddings"
    API_V1_STR: str = "/api/v1"

    # JWT auth for route access (see app/api/deps.py:require_scopes). Distinct
    # from JWT_SECRET_KEY/JWT_ALGORITHM (BaseAppSettings) which those two
    # also draw on - these add the expected 'iss'/'aud' claims.
    # JWT_ISSUER has no default: it must be set via env to whichever auth
    # service issues tokens for this deployment - there's no safe generic
    # default. JWT_AUDIENCE defaults to PROJECT_SLUG (see
    # _default_jwt_audience_from_project_slug below) when not set via env,
    # since every deployment of this service is itself the intended
    # audience.
    JWT_ISSUER: str
    JWT_AUDIENCE: str = ""

    @model_validator(mode="after")
    def _default_jwt_audience_from_project_slug(self) -> Settings:
        """Default JWT_AUDIENCE to PROJECT_SLUG when JWT_AUDIENCE wasn't set explicitly."""
        if not self.JWT_AUDIENCE:
            self.JWT_AUDIENCE = self.PROJECT_SLUG
        return self

    # Per-route rate limits; "default" (from BaseAppSettings.RATE_LIMIT_DEFAULT)
    # applies to any route not listed here.
    RATE_LIMIT_ENDPOINTS: dict[str, list[str]] = {
        "root": ["60 per minute"],
        "health": ["20 per minute"],
        "embed": ["60 per minute"],
    }

    # TEI embeddings server (see libs/ai/embeddings.py for the client built
    # from these, app/integrations/tei.py for the batching/validation
    # wrapper around it).
    # TEI_HOST is app-only since infra's .env has no host var - the
    # service's actual name/hostname on the shared Docker network is
    # "text-embeddings-inference". TEI_PORT (matching infra's .env var
    # name) is the host-facing port (docker-compose maps it to the
    # container's port 80) - not usable from inside the Docker network, so
    # it's kept here for reference only and NOT used to build the
    # connection URL. TEI_CONTAINER_PORT is app-only: TEI's actual internal
    # listen port.
    TEI_HOST: str = "text-embeddings-inference"
    TEI_PORT: int = 8086
    TEI_CONTAINER_PORT: int = 80
    TEI_REQUEST_TIMEOUT_SECONDS: float = 30.0
    # Must stay <= the TEI server's own --max-client-batch-size (32 by
    # default) - a larger value gets every request in the batch rejected
    # with 413, not just the overflow.
    TEI_CLIENT_BATCH_SIZE: int = 32
    # Must match the TEI server's actual --model-id's output dimension
    # (384 for the default BAAI/bge-small-en-v1.5) - used to validate every
    # response from TEI before returning it to a caller. A caller writing
    # these vectors into a fixed-width column (e.g. pgvector) is expected
    # to keep its own schema in sync with this value.
    TEI_EMBEDDING_DIM: int = 384

    # Voyage AI hosted embeddings API (see libs/ai/embeddings.py for the
    # client built from these, app/integrations/voyage.py for the
    # batching/validation wrapper around it). Voyage is only registered as
    # an available `provider` in POST /embed if VOYAGE_API_KEY is set - see
    # app/main.py's provider registry.
    VOYAGE_API_KEY: str = ""
    VOYAGE_MODEL: str = "voyage-3.5-lite"
    VOYAGE_REQUEST_TIMEOUT_SECONDS: float = 30.0
    # Must stay within Voyage's own per-request text-count limit for
    # VOYAGE_MODEL (see https://docs.voyageai.com/reference/embeddings-api).
    # Fallback used only when VOYAGE_MODEL has no entry in
    # libs.ai.tokenizers.VOYAGE_MODEL_LIMITS - see app/integrations/voyage.py.
    VOYAGE_CLIENT_BATCH_SIZE: int = 128

    # POST /api/v1/embed request bounds.
    EMBED_MAX_TEXTS_PER_REQUEST: int = 1000
    EMBED_MAX_TEXT_CHARS: int = 20_000


# Constructed once at import time and shared app-wide.
settings = Settings().apply_environment_defaults()
