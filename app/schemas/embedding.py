"""POST /api/v1/embed request/response schemas."""

from pydantic import BaseModel, Field, field_validator

from app.core.config import settings


class EmbedRequest(BaseModel):
    """POST /api/v1/embed request body."""

    texts: list[str] = Field(
        min_length=1,
        max_length=settings.EMBED_MAX_TEXTS_PER_REQUEST,
        description="Texts to embed, in order. Each item is capped at EMBED_MAX_TEXT_CHARS characters.",
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
