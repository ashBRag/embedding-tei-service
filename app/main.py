"""Application entry point: builds the FastAPI app and wires up shared infra.

The reusable pieces (logging, metrics, rate limiting, middleware) come from
libs/*; this file is only responsible for assembling them with *this*
project's settings and routes.
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import (
    FastAPI,
    Request,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.v1.api import api_router
from app.core.config import settings
from app.core.limiter import limiter
from app.integrations.base import EmbeddingProvider
from app.integrations.tei import TEIEmbeddingService
from app.integrations.voyage import VoyageEmbeddingService
from libs.ai import EmbeddingsSettings, VoyageEmbeddingsSettings, build_embeddings, build_voyage_embeddings
from libs.errors import register_exception_handlers
from libs.logging import setup_logging
from libs.metrics import (
    http_request_duration_seconds,
    http_requests_total,
    setup_metrics,
)
from libs.middleware import (
    LoggingContextMiddleware,
    MetricsMiddleware,
)

# Configure structlog once, at import time, before anything tries to log.
logger = setup_logging(settings, extra_context={"environment": settings.ENVIRONMENT.value})

# Single shared TEI client for this service - stateless, no DB/storage of its own.
# TEMPORARILY DISABLED for Voyage-only testing (see registry below) - restore
# both this and the "tei" registry entry to re-enable.
# fmt: off
# embeddings = build_embeddings(  # noqa: ERA001
#     EmbeddingsSettings(
#         base_url=f"http://{settings.TEI_HOST}:{settings.TEI_CONTAINER_PORT}",
#         timeout=settings.TEI_REQUEST_TIMEOUT_SECONDS,
#     )
# )
# fmt: on

# Provider registry for POST /embed's `provider` field (see
# app/integrations/base.py's EmbeddingProvider protocol). TEI is always
# registered; Voyage (and any future provider) is registered only when its
# config is present, so an unconfigured provider is a normal 400 at request
# time rather than a startup failure.
embedding_providers: dict[str, EmbeddingProvider] = {
    # "tei": TEIEmbeddingService(embeddings, logger=logger),  # disabled for Voyage-only testing  # noqa: ERA001
}
if settings.VOYAGE_API_KEY:
    voyage_embeddings = build_voyage_embeddings(
        VoyageEmbeddingsSettings(
            api_key=settings.VOYAGE_API_KEY,
            model=settings.VOYAGE_MODEL,
            timeout=settings.VOYAGE_REQUEST_TIMEOUT_SECONDS,
        )
    )
    embedding_providers["voyage"] = VoyageEmbeddingService(voyage_embeddings, logger=logger)

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description=settings.DESCRIPTION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
)

# Exposes GET /metrics for Prometheus to scrape.
setup_metrics(app)

# Starlette wraps middleware in reverse of add order (last added = outermost),
# so CORSMiddleware must be added last to sit outside ExceptionMiddleware -
# otherwise responses built by the exception handlers below (register_exception_handlers,
# the 429 handler) never pass back through it and error responses come back
# with no CORS headers, which browsers treat as an opaque failure.
#
# Order among the rest matters too: logging context must be bound before
# MetricsMiddleware runs, so metrics/logs emitted further down the chain see
# session_id/user_id.
app.add_middleware(
    LoggingContextMiddleware, jwt_secret_key=settings.JWT_SECRET_KEY, jwt_algorithm=settings.JWT_ALGORITHM
)
app.add_middleware(
    MetricsMiddleware,
    requests_total=http_requests_total,
    request_duration_seconds=http_request_duration_seconds,
)

# slowapi needs the limiter on app.state plus an exception handler for 429s.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Consistent {"error": {"code", "message", ...}} shape for AppError subclasses,
# HTTPException, validation errors, and any unhandled bug (last-resort 500).
register_exception_handlers(app, logger=logger, debug=settings.DEBUG)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# All project-specific routes are mounted under API_V1_STR (see app/api/v1/api.py).
app.include_router(api_router, prefix=settings.API_V1_STR)


def custom_openapi() -> dict[str, Any]:
    """Add the bearer-JWT security scheme so /docs shows an Authorize button.

    Auth here is a plain `Authorization: Bearer <token>` header checked by
    libs.auth.require_scopes (see app/api/deps.py), not FastAPI's own
    OAuth2/HTTPBearer dependency machinery - so the scheme has to be added to
    the OpenAPI schema by hand rather than inferred from a dependency.
    """
    if app.openapi_schema:
        return app.openapi_schema

    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    jwt_payload_schema = json.loads(
        (Path(__file__).resolve().parent / "schemas" / "jwt_payload.schema.json").read_text()
    )
    schema["components"].setdefault("schemas", {})["JWTPayload"] = {
        key: value for key, value in jwt_payload_schema.items() if not key.startswith("$")
    }
    schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": (
                "JWT issued by the auth service (see docs/AUTH.md). "
                "Payload claims are documented under the `JWTPayload` schema below. "
                "Required scopes, if any, are listed per-endpoint below."
            ),
        }
    }
    # Only under API_V1_STR requires a bearer token - "/", "/health", and
    # "/metrics" stay public.
    for path_str, path in schema["paths"].items():
        if not path_str.startswith(settings.API_V1_STR):
            continue
        for operation in path.values():
            operation["security"] = [{"BearerAuth": []}]

    app.openapi_schema = schema
    return app.openapi_schema


app.openapi = custom_openapi


@app.get("/")
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["root"][0])
async def root(request: Request):
    """Root endpoint returning basic API information."""
    logger.info("root_endpoint_called")
    return {
        "name": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "status": "healthy",
        "environment": settings.ENVIRONMENT.value,
        "swagger_url": "/docs",
        "redoc_url": "/redoc",
    }


@app.get("/health")
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["health"][0])
async def health_check(request: Request) -> dict[str, Any]:
    """Liveness + per-provider connectivity check.

    Overall status is "healthy" if at least one registered embedding
    provider is reachable (callers pick a provider per-request, so the
    service can still serve traffic with only one backend up), "degraded"
    if every registered provider is down.

    Returns:
        dict[str, Any]: Health status information
    """
    logger.info("health_check_called")

    provider_health = {name: await provider.health_check() for name, provider in embedding_providers.items()}
    any_healthy = any(provider_health.values())

    response = {
        "status": "healthy" if any_healthy else "degraded",
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT.value,
        "components": {
            "api": "healthy",
            **{name: "healthy" if healthy else "unhealthy" for name, healthy in provider_health.items()},
        },
        "timestamp": datetime.now(UTC).isoformat(),
    }

    status_code = status.HTTP_200_OK if any_healthy else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(content=response, status_code=status_code)
