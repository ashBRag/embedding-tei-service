"""POST /api/v1/embed request/response schemas."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.core.config import settings


class EmbedRequest(BaseModel):
    """POST /api/v1/embed request body."""

    texts: list[str] = Field(
        min_length=1,
        max_length=settings.EMBED_MAX_TEXTS_PER_REQUEST,
        description="Texts to embed, in order. Each item is capped at EMBED_MAX_TEXT_CHARS characters.",
    )
    provider: str = Field(
        default="tei",
        description=(
            "Which embedding backend to use. Available providers depend on deployment "
            "config (e.g. 'voyage' requires VOYAGE_API_KEY to be set) - an unknown or "
            "unconfigured provider is rejected with a 400 listing the available ones."
        ),
    )
    input_type: Literal["query", "document"] | None = Field(
        default=None,
        description=(
            "Optional hint for providers that support asymmetric query/document "
            "embeddings (currently Voyage AI) for better retrieval quality. "
            "Ignored by providers with no equivalent concept (e.g. TEI)."
        ),
    )

    @field_validator("texts")
    @classmethod
    def _check_text_lengths(cls, texts: list[str]) -> list[str]:
        """Reject any individual text over settings.EMBED_MAX_TEXT_CHARS - keeps one oversized item from blowing up the TEI payload_limit for the whole batch."""
        for text in texts:
            if len(text) > settings.EMBED_MAX_TEXT_CHARS:
                raise ValueError(f"each text must be at most {settings.EMBED_MAX_TEXT_CHARS} characters")
        return texts


class EmbedResponse(BaseModel):
    """POST /api/v1/embed response body."""

    embeddings: list[list[float]] = Field(description="One vector per input text, same order as the request.")
    dimension: int = Field(description="Length of every vector in `embeddings`.")
