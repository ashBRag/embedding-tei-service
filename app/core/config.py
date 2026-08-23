"""Project-specific application settings.

Generic env/logging/rate-limit machinery lives in libs.config;
this file only adds fields and defaults specific to *this* project.
"""

from libs.config import BaseAppSettings, Environment

__all__ = ["Environment", "settings"]


class Settings(BaseAppSettings):
    """This project's settings: adds identity/API fields on top of the base."""

    PROJECT_NAME: str = "Embedding Service"
    VERSION: str = "1.0.0"
    DESCRIPTION: str = "An API endpoint between TEI and consuming services: batches text and returns embeddings"
    API_V1_STR: str = "/api/v1"

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

    # POST /api/v1/embed request bounds.
    EMBED_MAX_TEXTS_PER_REQUEST: int = 1000
    EMBED_MAX_TEXT_CHARS: int = 20_000


# Constructed once at import time and shared app-wide.
settings = Settings().apply_environment_defaults()
