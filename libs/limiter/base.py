"""Rate limiter factory built on slowapi.

Kept as a factory (`build_limiter`) rather than a module-level singleton so
each project constructs its own `limiter` from its own settings, e.g.:

    from libs.limiter import build_limiter
    limiter = build_limiter(settings.RATE_LIMIT_DEFAULT)
"""

from slowapi import Limiter
from slowapi.util import get_remote_address


def build_limiter(default_limits: list[str]) -> Limiter:
    """Create a Limiter keyed by remote IP address.

    Args:
        default_limits: e.g. ["200 per day", "50 per hour"], applied to any
            route that doesn't declare its own @limiter.limit(...).
    """
    return Limiter(key_func=get_remote_address, default_limits=default_limits)
