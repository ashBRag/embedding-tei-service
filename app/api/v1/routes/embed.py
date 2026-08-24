"""POST /api/v1/embed: batch-embed texts through TEI and return the vectors."""

import httpx
from fastapi import APIRouter, Depends, Request, status

from app.api.deps import EmbeddingServiceDep, require_scopes
from app.core.config import settings
from app.core.limiter import limiter
from app.integrations.tei import EmbeddingValidationError
from app.schemas.embedding import EmbedRequest, EmbedResponse
from libs.errors import AppError

router = APIRouter(tags=["embedding"])


class UpstreamEmbeddingError(AppError):
    """TEI is unreachable, erroring, or returned a malformed response."""

    status_code = status.HTTP_502_BAD_GATEWAY
    code = "upstream_embedding_error"


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
    embedding_service: EmbeddingServiceDep,
) -> EmbedResponse:
    """Embed `texts` in order, batching requests to TEI within its own request-size limit.

    Validates that TEI returned exactly one correctly-sized vector per
    input text before responding - a mismatch raises rather than silently
    returning malformed output.
    """
    try:
        vectors = await embedding_service.embed(body.texts)
    except (httpx.HTTPError, EmbeddingValidationError) as exc:
        raise UpstreamEmbeddingError(f"TEI request failed: {exc}") from exc

    return EmbedResponse(embeddings=vectors, dimension=settings.TEI_EMBEDDING_DIM)
