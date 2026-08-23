"""Starlette middleware for request metrics and logging context propagation.

Both classes take their dependencies (JWT settings, metric objects) via
__init__ instead of importing project config directly, so they can be
`app.add_middleware(...)`'d in any project as-is.
"""

import time
from collections.abc import Callable

import jwt
from fastapi import Request
from prometheus_client import Counter, Histogram
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from libs.logging import bind_context, clear_context


class MetricsMiddleware(BaseHTTPMiddleware):
    """Records request count + duration into the given Prometheus metrics."""

    def __init__(self, app, requests_total: Counter, request_duration_seconds: Histogram):
        """Store the metric objects to update on every request."""
        super().__init__(app)
        self._requests_total = requests_total
        self._request_duration_seconds = request_duration_seconds

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Time the request and record its outcome, even if it raises."""
        start_time = time.time()

        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception:
            # Still record the 500 in metrics before re-raising for FastAPI's error handling.
            status_code = 500
            raise
        finally:
            duration = time.time() - start_time
            self._requests_total.labels(method=request.method, endpoint=request.url.path, status=status_code).inc()
            self._request_duration_seconds.labels(method=request.method, endpoint=request.url.path).observe(duration)

        return response


class LoggingContextMiddleware(BaseHTTPMiddleware):
    """Binds session_id (from JWT) and user_id (from request.state) to log context.

    Put this before other middleware so the fields it binds are present in
    logs emitted anywhere downstream during the same request.
    """

    def __init__(self, app, jwt_secret_key: str, jwt_algorithm: str = "HS256"):
        """Store the JWT settings used to decode the bearer token on each request."""
        super().__init__(app)
        self._jwt_secret_key = jwt_secret_key
        self._jwt_algorithm = jwt_algorithm

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Extract session_id from the bearer token (if any) and bind it for this request."""
        try:
            # Always start clean - avoids leaking context from a previous request
            # on the same worker/thread if a prior request's `finally` was skipped.
            clear_context()

            auth_header = request.headers.get("authorization")
            if auth_header and auth_header.startswith("Bearer "):
                token = auth_header.split(" ")[1]

                try:
                    payload = jwt.decode(token, self._jwt_secret_key, algorithms=[self._jwt_algorithm])
                    session_id = payload.get("sub")
                    if session_id:
                        bind_context(session_id=session_id)
                except jwt.PyJWTError:
                    # Invalid/expired token: don't fail the request here, let the
                    # route's own auth dependency reject it with a proper 401.
                    pass

            response = await call_next(request)

            # Route handlers/auth dependencies may set request.state.user_id after
            # verifying identity; pick it up now so it's logged for this request too.
            if hasattr(request.state, "user_id"):
                bind_context(user_id=request.state.user_id)

            return response
        finally:
            clear_context()
