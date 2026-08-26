"""POST /api/v1/embed: batch-embed texts through a configured provider and return the vectors."""

import httpx
from fastapi import APIRouter, Depends, Request, status

from app.api.deps import EmbeddingProvidersDep, require_scopes
from app.core.config import settings
from app.core.limiter import limiter
from app.integrations.base import EmbeddingValidationError
from app.schemas.embedding import EmbedRequest, EmbedResponse
from libs.errors import AppError

router = APIRouter(tags=["embedding"])


class UpstreamEmbeddingError(AppError):
    """The embedding provider is unreachable, erroring, or returned a malformed response."""

    status_code = status.HTTP_502_BAD_GATEWAY
    code = "upstream_embedding_error"


class UnknownProviderError(AppError):
    """The requested `provider` isn't registered (unrecognized, or not configured in this deployment)."""

    status_code = status.HTTP_400_BAD_REQUEST
    code = "unknown_embedding_provider"


@router.post(
    "/embed",
    response_model=EmbedResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_scopes())],
)
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["embed"][0])
async def embed_texts(
    request: Request,
    body: EmbedRequest,
    embedding_providers: EmbeddingProvidersDep,
) -> EmbedResponse:
    """Embed `texts` in order via `body.provider`, batching requests within that provider's own limits.

    Validates that the provider returned exactly one correctly-sized vector
    per input text before responding - a mismatch raises rather than
    silently returning malformed output.
    """
    provider = embedding_providers.get(body.provider)
    if provider is None:
        available = sorted(embedding_providers)
        raise UnknownProviderError(f"Unknown provider '{body.provider}'. Available: {available}")

    try:
        vectors = await provider.embed(body.texts, input_type=body.input_type)
    except (httpx.HTTPError, EmbeddingValidationError) as exc:
        raise UpstreamEmbeddingError(f"{provider.name} request failed: {exc}") from exc

    dimension = len(vectors[0]) if vectors else 0
    return EmbedResponse(embeddings=vectors, dimension=dimension)
