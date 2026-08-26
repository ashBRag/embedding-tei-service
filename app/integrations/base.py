"""Shared contract + batching helper for embedding providers.

`EmbeddingProvider` is the interface app/api routes and app/api/deps depend
on - adding a new backend (OpenAI, etc.) means writing one class that
satisfies this Protocol and registering it in app/main.py's provider
registry; no other layer (schema, routing, health check) needs to change.
"""

from typing import Any, Protocol

from libs.ai.embeddings import VoyageInputType


class _Logger(Protocol):
    """Structural type for whatever logger an EmbeddingProvider is given."""

    def error(self, event: str, **kwargs: Any) -> None: ...


class EmbeddingValidationError(Exception):
    """Raised when a provider's response doesn't match what was requested (count or dimension)."""


class EmbeddingProvider(Protocol):
    """What every embedding backend (TEI, Voyage, ...) must implement.

    `name` is the value callers pass as `EmbedRequest.provider` and the key
    each provider is registered under in app/main.py's registry.
    """

    name: str

    async def embed(self, texts: list[str], input_type: VoyageInputType = None) -> list[list[float]]:
        """Embed `texts` in order; `input_type` is a hint some providers ignore."""
        ...

    async def health_check(self) -> bool:
        """Return True if this provider is currently reachable, False on any error."""
        ...


async def embed_in_batches(
    texts: list[str],
    batch_size: int,
    embed_batch: Any,  # async (batch: list[str]) -> list[list[float]]
    validate: Any,  # (batch: list[str], vectors: list[list[float]]) -> None
    on_error: Any,  # (batch: list[str], exc: Exception) -> None
) -> list[list[float]]:
    """Embed `texts` in order, batching requests of at most `batch_size`.

    Shared by every provider's EmbeddingProvider implementation so the
    batching/validation/error-logging shape stays identical across
    providers even though each provider's HTTP call, batch limit, and
    validation rule differ.
    """
    if not texts:
        return []

    vectors: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        try:
            batch_vectors = await embed_batch(batch)
        except Exception as exc:
            on_error(batch, exc)
            raise
        validate(batch, batch_vectors)
        vectors.extend(batch_vectors)

    return vectors
