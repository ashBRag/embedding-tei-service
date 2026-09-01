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
from libs.ai.rate_limit import ModelLimits, RateLimiter
from libs.ai.tokenizers import (
    VOYAGE_MODEL_LIMITS,
    VOYAGE_TOKENIZER_REPOS,
    VoyageModelLimits,
    count_tokens,
    get_tokenizer,
)

__all__ = [
    "VOYAGE_MODEL_LIMITS",
    "VOYAGE_TOKENIZER_REPOS",
    "EmbeddingsSettings",
    "ModelLimits",
    "RateLimiter",
    "TeiEmbeddings",
    "VoyageEmbeddings",
    "VoyageEmbeddingsSettings",
    "VoyageModelLimits",
    "build_embeddings",
    "build_voyage_embeddings",
    "count_tokens",
    "get_tokenizer",
]
