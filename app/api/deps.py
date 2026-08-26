"""Shared FastAPI dependency providers for the API layer.

Builds request-scoped service instances from the app-wide singletons
constructed in app/main.py (embedding provider registry, logger).
"""

from functools import partial
from typing import Annotated

from fastapi import Depends

from app.core.config import settings
from app.integrations.base import EmbeddingProvider
from libs.auth import require_scopes as _require_scopes


def get_embedding_providers() -> dict[str, EmbeddingProvider]:
    """Return the app-wide registry of available embedding providers, keyed by name.

    Built once at startup in app/main.py from whichever providers have
    config present (e.g. Voyage is only registered if VOYAGE_API_KEY is
    set). Routes pick the right provider out of this dict at request time,
    once the request body (and its `provider` field) has been parsed.
    """
    from app.main import embedding_providers

    return embedding_providers


EmbeddingProvidersDep = Annotated[dict[str, EmbeddingProvider], Depends(get_embedding_providers)]


# Binds this project's JWT settings to the generic libs.auth dependency
# factory - route code calls require_scopes() same as before.
require_scopes = partial(
    _require_scopes,
    secret_key=settings.JWT_SECRET_KEY,
    algorithm=settings.JWT_ALGORITHM,
    issuer=settings.JWT_ISSUER,
    audience=settings.JWT_AUDIENCE,
)
