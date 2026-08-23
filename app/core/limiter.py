"""Shared rate limiter instance.

Split out from app/main.py so route modules can import it directly for
`@limiter.limit(...)` decorators without a circular import (main.py
imports the route modules via app.api.v1.api, so route modules can't
import `limiter` back from main.py at decoration time).
"""

from app.core.config import settings
from libs.limiter import build_limiter

limiter = build_limiter(settings.RATE_LIMIT_DEFAULT)
