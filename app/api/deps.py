"""Shared FastAPI dependency providers for the API layer.

Builds request-scoped service instances from the app-wide singletons
constructed in app/main.py (embeddings client, logger).
"""

from functools import partial
from typing import Annotated

from fastapi import Depends

from app.core.config import settings
from app.integrations.tei import TEIEmbeddingService
from libs.auth import require_scopes as _require_scopes


def get_embedding_service() -> TEIEmbeddingService:
    """Build a TEIEmbeddingService wrapping the app-wide TEI client."""
    from app.main import embeddings, logger

    return TEIEmbeddingService(embeddings, logger=logger)


EmbeddingServiceDep = Annotated[TEIEmbeddingService, Depends(get_embedding_service)]


# Binds this project's JWT settings to the generic libs.auth dependency
# factory - route code calls require_scopes() same as before.
require_scopes = partial(
    _require_scopes,
    secret_key=settings.JWT_SECRET_KEY,
    algorithm=settings.JWT_ALGORITHM,
    issuer=settings.JWT_ISSUER,
    audience=settings.JWT_AUDIENCE,
)
