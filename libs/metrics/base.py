"""Prometheus metrics: standard HTTP request counters/timers + a /metrics route.

Fully generic — no project-specific label values or business metrics live
here. Add those in the consuming project (e.g. app/core/metrics.py) by
importing http_requests_total / http_request_duration_seconds if you need to
reuse them, or by defining new Counters/Histograms alongside setup_metrics().
"""

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response

# Count every HTTP request, labeled by method/path/status - the bread-and-butter
# metric for building request-rate and error-rate dashboards/alerts.
http_requests_total = Counter(
    "http_requests_total",
    "Total number of HTTP requests",
    ["method", "endpoint", "status"],
)

# Latency histogram, so Grafana/Prometheus can compute p50/p95/p99 request duration.
http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
)

# Generic gauge a project can update from its own DB pool/connection code.
db_connections = Gauge("db_connections", "Number of active database connections")


async def metrics_endpoint(_: Request) -> Response:
    """Render all registered Prometheus metrics in the standard exposition format."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


def setup_metrics(app: Starlette) -> None:
    """Mount the /metrics scrape endpoint on the given app."""
    app.add_route("/metrics", metrics_endpoint)
