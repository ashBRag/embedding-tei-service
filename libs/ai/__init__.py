"""Embeddings clients: TEI (self-hosted) and Voyage AI (hosted).

Self-contained: no dependency on any other libs/* package.
"""

from libs.ai.embeddings import (
    EmbeddingsSettings,
    TeiEmbeddings,
    VoyageEmbeddings,
    VoyageEmbeddingsSettings,
    build_embeddings,
    build_voyage_embeddings,
)

__all__ = [
    "EmbeddingsSettings",
    "TeiEmbeddings",
    "VoyageEmbeddings",
    "VoyageEmbeddingsSettings",
    "build_embeddings",
    "build_voyage_embeddings",
]
