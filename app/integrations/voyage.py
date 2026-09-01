"""Voyage AI-backed EmbeddingProvider: batches text through Voyage's hosted API.

Wraps libs.ai.embeddings.VoyageEmbeddings (the project's Voyage HTTP client)
rather than opening a second httpx client - this module owns only the
EmbeddingProvider contract (batching, rate limiting, order/count/dimension
validation), not the HTTP call itself.

When the configured model has entries in both settings.VOYAGE_MODEL_LIMITS
and libs.ai.tokenizers.VOYAGE_TOKENIZER_REPOS, batching is token-aware and
rate-limited: requests are split so no single request exceeds the model's
max_batch_size or a safe share of its TPM budget, and every request waits on
a RateLimiter before going out - so normal traffic volume never draws a 429
from Voyage's own TPM/RPM caps. Otherwise this falls back to plain
count-based batching (same as TEI) with no TPM/RPM throttling.

Unlike TEI, Voyage's output dimension isn't fixed per deployment (it depends
on which model is configured, and some models support variable output
dimensions) - so validation checks internal consistency (every vector in a
response is the same length) rather than against a hardcoded constant.

No DB access here - this integration only ever sees plain text strings in,
and returns vectors out.
"""

from app.core.config import settings
from app.integrations.base import EmbeddingValidationError, _Logger, embed_in_batches, embed_in_rate_limited_batches
from libs.ai.embeddings import VoyageEmbeddings, VoyageInputType
from libs.ai.rate_limit import ModelLimits, RateLimiter
from libs.ai.tokenizers import VOYAGE_TOKENIZER_REPOS, count_tokens

__all__ = ["VoyageEmbeddingService"]


class VoyageEmbeddingService:
    """Embeds text via Voyage AI, batching requests and validating the response."""

    name = "voyage"

    def __init__(
        self,
        voyage_embeddings: VoyageEmbeddings,
        model: str = settings.VOYAGE_MODEL,
        batch_size: int = settings.VOYAGE_CLIENT_BATCH_SIZE,
        logger: _Logger | None = None,
    ):
        """Store the Voyage client, batching/rate-limit config, and an optional logger.

        `model` selects which entry of settings.VOYAGE_MODEL_LIMITS (TPM/RPM/
        max_batch_size) and libs.ai.tokenizers.VOYAGE_TOKENIZER_REPOS (token
        counting) this instance uses; it should match the model
        `voyage_embeddings` actually calls. `batch_size` is the fallback
        per-request text-count cap used when `model` has no entry in
        VOYAGE_MODEL_LIMITS - it must stay within Voyage's own per-request
        text-count limit for the configured model either way.

        Rate-limited, token-aware batching only applies when `model` has
        entries in *both* VOYAGE_MODEL_LIMITS and VOYAGE_TOKENIZER_REPOS
        (token counting needs a tokenizer); otherwise this falls back to
        plain count-based batching with no TPM/RPM throttling, same as
        before this feature existed.
        """
        self._voyage = voyage_embeddings
        self._model = model
        self._logger = logger

        limits = settings.VOYAGE_MODEL_LIMITS.get(model)
        self._rate_limited = limits is not None and model in VOYAGE_TOKENIZER_REPOS
        self._max_batch_size = limits["max_batch_size"] if limits else batch_size

        if self._rate_limited:
            self._rate_limiter = RateLimiter(
                ModelLimits(tpm=limits["tpm"], rpm=limits["rpm"], max_batch_size=self._max_batch_size)
            )
            # A single request should never claim more than half the TPM
            # budget, so several concurrent requests can share the window
            # without one batch starving the rest.
            self._max_tokens_per_batch = max(limits["tpm"] // 2, 1)

    async def embed(self, texts: list[str], input_type: VoyageInputType = None) -> list[list[float]]:
        """Embed `texts` in order, batching requests within this model's configured limits.

        Args:
            texts: The strings to embed.
            input_type: Voyage's "query" vs "document" hint for better
                retrieval quality; None sends no hint.

        Raises:
            EmbeddingValidationError: If any batch's response from Voyage
                doesn't have one vector per input text, or vectors within
                the same response have inconsistent dimensions.

        Returns:
            list[list[float]]: One embedding vector per input text, in the
            same order as `texts`. `[]` if `texts` is empty.
        """

        async def embed_batch(batch: list[str]) -> list[list[float]]:
            return await self._voyage.aembed_documents(batch, input_type=input_type)

        if self._rate_limited:
            return await embed_in_rate_limited_batches(
                texts,
                self._max_batch_size,
                self._max_tokens_per_batch,
                count_tokens=lambda text: count_tokens(self._model, text),
                rate_limiter=self._rate_limiter,
                embed_batch=embed_batch,
                validate=self._validate,
                on_error=self._log_error,
            )

        return await embed_in_batches(
            texts,
            self._max_batch_size,
            embed_batch=embed_batch,
            validate=self._validate,
            on_error=self._log_error,
        )

    async def health_check(self) -> bool:
        """Return True if a minimal Voyage embed call succeeds, False on any error."""
        return await self._voyage.health_check()

    def _log_error(self, batch: list[str], exc: Exception) -> None:
        # Text content itself is never logged (may carry sensitive
        # document text) - only its size.
        if self._logger is not None:
            self._logger.error(
                "voyage_embed_request_failed",
                batch_size=len(batch),
                batch_chars=sum(len(t) for t in batch),
                max_text_chars=max((len(t) for t in batch), default=0),
                error_type=type(exc).__name__,
            )

    @staticmethod
    def _validate(batch: list[str], vectors: list[list[float]]) -> None:
        """Check Voyage returned exactly one vector per input text, all the same dimension."""
        if len(vectors) != len(batch):
            raise EmbeddingValidationError(f"Voyage returned {len(vectors)} embeddings for {len(batch)} inputs")

        dims = {len(vector) for vector in vectors}
        if len(dims) > 1:
            raise EmbeddingValidationError(f"Voyage returned embeddings with inconsistent dimensions: {dims}")
