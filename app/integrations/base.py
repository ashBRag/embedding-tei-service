"""Shared contract + batching helper for embedding providers.

`EmbeddingProvider` is the interface app/api routes and app/api/deps depend
on - adding a new backend (OpenAI, etc.) means writing one class that
satisfies this Protocol and registering it in app/main.py's provider
registry; no other layer (schema, routing, health check) needs to change.
"""

from typing import Any, Protocol

from libs.ai.embeddings import VoyageInputType
from libs.ai.rate_limit import RateLimiter


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


def plan_token_aware_batches(
    texts: list[str],
    max_batch_size: int,
    max_tokens_per_batch: int,
    count_tokens: Any,  # (text: str) -> int
) -> list[list[str]]:
    """Split `texts` into batches respecting both an item-count cap and a token-count cap.

    Greedy: adds texts to the current batch until either cap would be
    exceeded, then starts a new batch. A single text whose own token count
    exceeds `max_tokens_per_batch` still gets its own one-item batch (rather
    than raising) - the provider's own per-request limit is left to reject
    it if it's truly too large; this function only avoids *needlessly*
    combining texts past the budget.
    """
    if not texts:
        return []

    batches: list[list[str]] = []
    current: list[str] = []
    current_tokens = 0

    for text in texts:
        tokens = count_tokens(text)
        would_exceed_tokens = current and current_tokens + tokens > max_tokens_per_batch
        would_exceed_count = len(current) >= max_batch_size
        if would_exceed_tokens or would_exceed_count:
            batches.append(current)
            current = []
            current_tokens = 0

        current.append(text)
        current_tokens += tokens

    if current:
        batches.append(current)

    return batches


async def embed_in_rate_limited_batches(
    texts: list[str],
    max_batch_size: int,
    max_tokens_per_batch: int,
    count_tokens: Any,  # (text: str) -> int
    rate_limiter: RateLimiter,
    embed_batch: Any,  # async (batch: list[str]) -> list[list[float]]
    validate: Any,  # (batch: list[str], vectors: list[list[float]]) -> None
    on_error: Any,  # (batch: list[str], exc: Exception) -> None
) -> list[list[float]]:
    """Embed `texts` in order, batching by count + token budget, throttled by `rate_limiter`.

    Like `embed_in_batches`, but batches are planned with
    `plan_token_aware_batches` (so no single request can exceed the
    provider's per-minute token budget on its own) and each batch waits on
    `rate_limiter.acquire` before the HTTP call, so the caller never needs
    to handle 429s from ordinary traffic volume.
    """
    if not texts:
        return []

    batches = plan_token_aware_batches(texts, max_batch_size, max_tokens_per_batch, count_tokens)

    vectors: list[list[float]] = []
    for batch in batches:
        batch_tokens = sum(count_tokens(text) for text in batch)
        await rate_limiter.acquire(batch_tokens)
        try:
            batch_vectors = await embed_batch(batch)
        except Exception as exc:
            on_error(batch, exc)
            raise
        validate(batch, batch_vectors)
        vectors.extend(batch_vectors)

    return vectors
