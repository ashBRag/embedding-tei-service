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

### Payload shape

```json
{
  "sub": "user-123",
  "exp": 1790277655,
  "iat": 1787685655,
  "iss": "https://auth.example.com",
  "aud": "embedding-service",
  "scope": "orders:read orders:write",
  "jti": "b3f1c2a0-6e4d-4b8a-9f21-0d6e5a7c9f10"
}
```

JSON Schema: [`app/schemas/jwt_payload.schema.json`](../app/schemas/jwt_payload.schema.json).

### Claim values

| Claim | Type | Example | Notes |
|---|---|---|---|
| `sub` | string | `"user-123"` | Calling principal's unique id (opaque identifier, not an email). Becomes `request.state.user_id`. Required. |
| `exp` | integer, Unix timestamp (seconds) | `1798761600` | Expiry. PyJWT rejects the token once `now > exp`. Typically short-lived. Required. |
| `iat` | integer, Unix timestamp (seconds) | `1798758000` | Issued-at; must be `<= exp`. Not actively enforced beyond being present. Required. |
| `iss` | string | `"https://auth.example.com"` | Must exactly match this service's `JWT_ISSUER` (no default - set per deployment to whichever auth service issues tokens). Mismatch is a 401 even with a valid signature. Required. |
| `aud` | string | `"embedding-service"` | Must exactly match this service's `JWT_AUDIENCE` (defaults to `PROJECT_SLUG` if not set explicitly). Prevents a token minted for one service being replayed against another. Required. |
| `scope` | string, space-separated | `"orders:read orders:write"` | Permissions granted. Route must find all its required scopes here or gets 403. Optional - missing/empty means no scopes granted. |
| `jti` | string | a UUID | Unique id for this token instance. Not validated by this service, just passed through to `TokenPayload.jti` for the caller's own use (e.g. revocation, audit logs). Optional. |

The token must also be signed with the configured `JWT_ALGORITHM`/`JWT_SECRET_KEY` -
a well-formed payload with a bad signature is rejected before any claims are read.

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
# JWT_AUDIENCE=embedding-service   # optional - defaults to PROJECT_SLUG
```

`JWT_SECRET_KEY`/`JWT_ALGORITHM` are shared with `LoggingContextMiddleware`
(decodes the token to bind `session_id` to logs, best-effort, never rejects
a request on its own). `JWT_ISSUER`/`JWT_AUDIENCE` are used only for route
auth enforcement. `JWT_ISSUER` has no default and must be set explicitly;
`JWT_AUDIENCE` defaults to `PROJECT_SLUG` (this service's own identifier)
when not set.
