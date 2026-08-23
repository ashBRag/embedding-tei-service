"""TEI-backed EmbeddingService: batches text through the local TEI HTTP API.

Wraps libs.ai.embeddings.TeiEmbeddings (the project's existing TEI HTTP
client) rather than opening a second httpx client - this module owns only
the EmbeddingService contract (batching, order/count/dimension validation),
not the HTTP call itself.

No DB access here - this integration only ever sees plain text strings in,
and returns vectors out.
"""

from typing import Any, Protocol

from app.core.config import settings
from libs.ai.embeddings import TeiEmbeddings


class _Logger(Protocol):
    """Structural type for whatever logger TEIEmbeddingService is given."""

    def error(self, event: str, **kwargs: Any) -> None: ...


class EmbeddingValidationError(Exception):
    """Raised when TEI's response doesn't match what was requested (count or dimension)."""


class TEIEmbeddingService:
    """Embeds text via a TEI server, batching requests and validating the response."""

    def __init__(
        self,
        tei_embeddings: TeiEmbeddings,
        batch_size: int = settings.TEI_CLIENT_BATCH_SIZE,
        expected_dim: int = settings.TEI_EMBEDDING_DIM,
        logger: _Logger | None = None,
    ):
        """Store the TEI client, batching/validation config, and an optional logger.

        `batch_size` defaults from settings.TEI_CLIENT_BATCH_SIZE, which
        must stay <= the TEI server's own --max-client-batch-size (32 by
        default) - a larger value gets every request in the batch rejected
        with 413, not just the overflow.

        `expected_dim` defaults from settings.TEI_EMBEDDING_DIM, which must
        match the actual output dimension of the TEI server's --model-id -
        callers on the other side of this service's API (e.g. a caller
        writing vectors into a fixed-width pgvector column) are expected to
        keep their own schema in sync with this value.
        """
        self._tei = tei_embeddings
        self._batch_size = batch_size
        self._expected_dim = expected_dim
        self._logger = logger

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed `texts` in order, batching requests of at most `batch_size`.

        Args:
            texts: The strings to embed.

        Raises:
            EmbeddingValidationError: If any batch's response from TEI
                doesn't have one vector per input text, or a vector isn't
                `expected_dim` long.

        Returns:
            list[list[float]]: One embedding vector per input text, in the
            same order as `texts`. `[]` if `texts` is empty.
        """
        if not texts:
            return []

        vectors: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            batch = texts[start : start + self._batch_size]
            try:
                batch_vectors = await self._tei.aembed_documents(batch)
            except Exception as exc:
                # Text content itself is never logged (may carry sensitive
                # document text) - only its size, since that's what
                # determines whether TEI's payload_limit trips.
                if self._logger is not None:
                    self._logger.error(
                        "tei_embed_request_failed",
                        batch_size=len(batch),
                        batch_chars=sum(len(t) for t in batch),
                        max_text_chars=max((len(t) for t in batch), default=0),
                        error_type=type(exc).__name__,
                    )
                raise
            self._validate(batch, batch_vectors)
            vectors.extend(batch_vectors)

        return vectors

    def _validate(self, batch: list[str], vectors: list[list[float]]) -> None:
        """Check TEI returned exactly one correctly-sized vector per input text."""
        if len(vectors) != len(batch):
            raise EmbeddingValidationError(f"TEI returned {len(vectors)} embeddings for {len(batch)} inputs")

        for vector in vectors:
            if len(vector) != self._expected_dim:
                raise EmbeddingValidationError(
                    f"TEI returned a {len(vector)}-dim embedding, expected {self._expected_dim}"
                )
