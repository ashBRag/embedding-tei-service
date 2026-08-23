"""Prometheus HTTP metrics + a /metrics scrape route.

Self-contained: no dependency on any other libs/* package.
"""

from libs.metrics.base import (
    db_connections,
    http_request_duration_seconds,
    http_requests_total,
    metrics_endpoint,
    setup_metrics,
)

__all__ = [
    "db_connections",
    "http_request_duration_seconds",
    "http_requests_total",
    "metrics_endpoint",
    "setup_metrics",
]
