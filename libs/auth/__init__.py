"""JWT bearer-token verification + scope enforcement for FastAPI routes.

Depends only on libs.errors - secret/algorithm/issuer/audience are passed in
by the caller, so no dependency on libs.config is required at import time.
"""

from libs.auth.base import TokenPayload, require_scopes

__all__ = ["TokenPayload", "require_scopes"]
