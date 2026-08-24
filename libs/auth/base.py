"""JWT bearer-token verification + scope enforcement for FastAPI routes.

Self-contained: depends only on libs.errors (for the 401/403 response
shapes). Issuer/audience/secret/algorithm are passed in by the caller
(a project's settings object), not read from libs.config directly.
"""

import jwt
from fastapi import Request

from libs.errors import ForbiddenError, UnauthorizedError


class TokenPayload:
    """Verified JWT claims for the calling principal, as returned by `require_scopes`."""

    def __init__(self, sub: str, scopes: set[str], jti: str | None):
        """Store the claims routes/services are actually expected to use."""
        self.sub = sub
        self.scopes = scopes
        self.jti = jti


def require_scopes(
    *required_scopes: str,
    secret_key: str,
    algorithm: str,
    issuer: str,
    audience: str,
):
    """Build a FastAPI dependency that verifies the bearer JWT and requires all `required_scopes`.

    Verifies signature, expiry, issuer, and audience against the given
    `secret_key`/`algorithm`/`issuer`/`audience`, then checks the
    space-separated `scope` claim contains every scope in `required_scopes`.
    Raises UnauthorizedError (401) for a missing/invalid/expired token and
    ForbiddenError (403) for valid credentials lacking the required scope(s).

    Usage (project's own app/api/deps.py):

        require_orders_scopes = partial(
            require_scopes,
            secret_key=settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
            issuer=settings.JWT_ISSUER,
            audience=settings.JWT_AUDIENCE,
        )

        @router.post("/mask", dependencies=[Depends(require_orders_scopes("orders:read", "orders:write"))])
    """

    async def _verify(request: Request) -> TokenPayload:
        auth_header = request.headers.get("authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            raise UnauthorizedError("Missing bearer token")

        token = auth_header.removeprefix("Bearer ").strip()
        if not token:
            raise UnauthorizedError("Missing bearer token")

        try:
            payload = jwt.decode(
                token,
                secret_key,
                algorithms=[algorithm],
                issuer=issuer,
                audience=audience,
                options={"require": ["exp", "iat", "sub", "iss", "aud"]},
            )
        except jwt.PyJWTError as exc:
            raise UnauthorizedError("Invalid or expired token") from exc

        sub = payload.get("sub")
        if not sub:
            raise UnauthorizedError("Token missing 'sub' claim")

        token_scopes = set(payload.get("scope", "").split())
        missing = set(required_scopes) - token_scopes
        if missing:
            raise ForbiddenError(f"Missing required scope(s): {', '.join(sorted(missing))}")

        request.state.user_id = sub
        return TokenPayload(sub=sub, scopes=token_scopes, jti=payload.get("jti"))

    return _verify
