"""Shared FastAPI dependency providers for the API layer.

Builds request-scoped service instances from the app-wide singletons
constructed in app/main.py (embeddings client, logger).
"""

from typing import Annotated

from fastapi import Depends

from app.integrations.tei import TEIEmbeddingService


def get_embedding_service() -> TEIEmbeddingService:
    """Build a TEIEmbeddingService wrapping the app-wide TEI client."""
    from app.main import embeddings, logger

    return TEIEmbeddingService(embeddings, logger=logger)


EmbeddingServiceDep = Annotated[TEIEmbeddingService, Depends(get_embedding_service)]
