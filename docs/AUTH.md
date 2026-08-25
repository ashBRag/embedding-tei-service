# Authentication

All routes under `API_V1_STR` (`/api/v1/...`) require a JWT bearer token.
`/`, `/health`, and `/metrics` stay public.

## Sending a request

```
Authorization: Bearer <jwt>
```

```bash
curl -X POST http://localhost:8000/api/v1/embed \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"texts": ["hello world"]}'
```

In Swagger UI (`/docs`), click **Authorize** and paste the raw token (no
`Bearer ` prefix - Swagger adds it).

## Token requirements

Verification is done by `libs.auth.require_scopes` (`libs/auth/base.py`),
wired to this project's settings in `app/api/deps.py`. A token is accepted
only if:

| Claim | Requirement |
|---|---|
| Signature | Valid for `JWT_SECRET_KEY` / `JWT_ALGORITHM` |
| `exp`, `iat`, `sub`, `iss`, `aud` | Present |
| `iss` | Equals `JWT_ISSUER` |
| `aud` | Equals `JWT_AUDIENCE` |
| `scope` | Space-separated string containing every scope required by the route (see below) |

A missing, malformed, expired, or bad-signature token gets `401 Unauthorized`.
A valid token missing a required scope gets `403 Forbidden`.

`sub` is stashed on `request.state.user_id` for logging/metrics; the full
decoded payload (`sub`, `scopes`, `jti`) is returned to the route as a
`TokenPayload`.

## Required scopes per endpoint

| Endpoint | Required scopes |
|---|---|
| `POST /api/v1/embed` | none (any valid token for this issuer/audience) |

Routes declare their own required scopes via
`Depends(require_scopes("scope:one", "scope:two"))` - see
`app/api/v1/routes/embed.py`.

## Configuration

Set in `.env.<environment>` (see `.env.example`):

```
JWT_SECRET_KEY="your-jwt-secret-key"
JWT_ALGORITHM=HS256
JWT_ISSUER="https://auth.example.com"
JWT_AUDIENCE="service-b"
```

`JWT_SECRET_KEY`/`JWT_ALGORITHM` are shared with `LoggingContextMiddleware`
(decodes the token to bind `session_id` to logs, best-effort, never rejects
a request on its own). `JWT_ISSUER`/`JWT_AUDIENCE` are used only for route
auth enforcement.
