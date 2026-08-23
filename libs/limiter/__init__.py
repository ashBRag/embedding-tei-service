"""Rate limiter factory built on slowapi.

Self-contained: no dependency on any other libs/* package.
"""

from libs.limiter.base import build_limiter

__all__ = ["build_limiter"]
