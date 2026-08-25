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
from libs.ai import EmbeddingsSettings, build_embeddings
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
embeddings = build_embeddings(
    EmbeddingsSettings(
        base_url=f"http://{settings.TEI_HOST}:{settings.TEI_CONTAINER_PORT}",
        timeout=settings.TEI_REQUEST_TIMEOUT_SECONDS,
    )
)

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
    """Liveness + TEI connectivity check.

    Returns:
        dict[str, Any]: Health status information
    """
    logger.info("health_check_called")

    tei_healthy = await embeddings.health_check()

    response = {
        "status": "healthy" if tei_healthy else "degraded",
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT.value,
        "components": {
            "api": "healthy",
            "tei": "healthy" if tei_healthy else "unhealthy",
        },
        "timestamp": datetime.now(UTC).isoformat(),
    }

    status_code = status.HTTP_200_OK if tei_healthy else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(content=response, status_code=status_code)
