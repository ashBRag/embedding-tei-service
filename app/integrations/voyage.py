"""Voyage AI-backed EmbeddingProvider: batches text through Voyage's hosted API.

Wraps libs.ai.embeddings.VoyageEmbeddings (the project's Voyage HTTP client)
rather than opening a second httpx client - this module owns only the
EmbeddingProvider contract (batching, order/count/dimension validation), not
the HTTP call itself.

Unlike TEI, Voyage's output dimension isn't fixed per deployment (it depends
on which model is configured, and some models support variable output
dimensions) - so validation checks internal consistency (every vector in a
response is the same length) rather than against a hardcoded constant.

No DB access here - this integration only ever sees plain text strings in,
and returns vectors out.
"""

from app.core.config import settings
from app.integrations.base import EmbeddingValidationError, _Logger, embed_in_batches
from libs.ai.embeddings import VoyageEmbeddings, VoyageInputType

__all__ = ["VoyageEmbeddingService"]


class VoyageEmbeddingService:
    """Embeds text via Voyage AI, batching requests and validating the response."""

    name = "voyage"

    def __init__(
        self,
        voyage_embeddings: VoyageEmbeddings,
        batch_size: int = settings.VOYAGE_CLIENT_BATCH_SIZE,
        logger: _Logger | None = None,
    ):
        """Store the Voyage client, batching config, and an optional logger.

        `batch_size` defaults from settings.VOYAGE_CLIENT_BATCH_SIZE, which
        must stay within Voyage's own per-request text-count limit for the
        configured model.
        """
        self._voyage = voyage_embeddings
        self._batch_size = batch_size
        self._logger = logger

    async def embed(self, texts: list[str], input_type: VoyageInputType = None) -> list[list[float]]:
        """Embed `texts` in order, batching requests of at most `batch_size`.

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

        return await embed_in_batches(
            texts,
            self._batch_size,
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
