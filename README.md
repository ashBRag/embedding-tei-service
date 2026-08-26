# Embedding Service

A thin API endpoint in front of multiple embedding backends (TEI, Voyage AI,
...) for its consuming services. Takes a batch of texts, re-batches them
within the chosen provider's own request-size limit, validates the
response, and returns one vector per input text - in order.

Stateless: no database, no storage. A caller (e.g. a RAG backend writing
vectors into pgvector) owns persistence and schema on its own side.

## Pipeline

```
texts (POST /api/v1/embed, provider: "tei" | "voyage" | ...)
  │
  ▼
Select provider    look up `provider` in the registry built at startup from
  │                whichever providers have config present (see
  │                app/main.py, app/integrations/base.py's EmbeddingProvider)
  ▼
Batch              re-batched into groups of at most that provider's own
  │                client batch size (TEI_CLIENT_BATCH_SIZE / 
  │                VOYAGE_CLIENT_BATCH_SIZE) - must stay within the
  │                backend's own request-size limit, or the whole batch fails
  ▼
Embed              each batch sent to the provider's embeddings endpoint
  │
  ▼
Validate           one vector per input text, all the same dimension - a
  │                mismatch raises rather than returning malformed output
  ▼
Return             {embeddings: [[...], ...], dimension: N}, same order as input
```

## API

| Endpoint | Purpose |
|---|---|
| `POST /api/v1/embed` | Embeds `texts` (max `EMBED_MAX_TEXTS_PER_REQUEST` items, each up to `EMBED_MAX_TEXT_CHARS` characters) via `provider` (default `"tei"`; `"voyage"` if `VOYAGE_API_KEY` is set) and returns one vector per input text, in order. `input_type: "query" | "document"` is an optional hint some providers (Voyage) use for better retrieval quality. |

All `/api/v1/...` routes require a JWT bearer token - see [docs/AUTH.md](docs/AUTH.md).

## Adding a new provider

1. Add an `Embeddings` client to `libs/ai/embeddings.py` (sync + async HTTP calls to the provider's API).
2. Add an `app/integrations/<provider>.py` implementing `EmbeddingProvider` (see `app/integrations/base.py`) - batching, validation, error logging, using the shared `embed_in_batches` helper.
3. Add its config fields to `app/core/config.py` and `.env.example`.
4. Register it in `app/main.py`'s `embedding_providers` dict, guarded by its own config being present.

No changes needed to the request schema, routing, deps, or `/health` - all provider-agnostic.

## Project layout

```
app/
  main.py             # Wires everything together; builds the provider registry
  core/                 # Settings, rate limiter
  api/deps.py            # Shared FastAPI dependency providers (provider registry)
  api/v1/routes/         # embed
  schemas/               # Request/response shapes
  integrations/           # EmbeddingProvider implementations: batching + response validation
                          # (base.py: shared protocol/helper, tei.py, voyage.py)

libs/                    # Small, reusable, project-agnostic infra helpers
                          # (logging, metrics, errors, rate limiting, the TEI
                          #  and Voyage HTTP clients themselves)
```

## Requirements

- Python >= 3.14
- [uv](https://docs.astral.sh/uv/)
- A running TEI server (see `docker-compose.yml` / the shared infra stack)

## Setup

```bash
make install                        # uv sync
cp .env.example .env.development    # fill in real values (JWT secret, TEI host, ...)
```

## Running

```bash
make dev     # uvicorn with reload, port 8000
make prod    # uvicorn, no reload
```

Or directly:

```bash
uv run uvicorn app.main:app --reload --port 8000
```

Check it's up:

- `GET /` - basic service info
- `GET /health` - liveness + per-provider connectivity (`degraded`/503 only if every registered provider is unreachable)
- `GET /docs` - Swagger UI
- `GET /metrics` - Prometheus scrape endpoint

## Docker

```bash
make docker-up     # creates backend-internal if missing, builds, starts (ENV=development by default)
make docker-logs
make docker-down
```

Pass `ENV=staging` / `ENV=production` to target a different `.env.<ENV>` file.

## Configuration

Settings are loaded via `pydantic-settings` from `.env.<APP_ENV>` (falling back to
`.env.local` / `.env`), with environment-specific defaults applied on top - see
`app/core/config.py` for this project's fields. See `.env.example` for the full
list of variables.

## Linting & tests

```bash
make lint     # ruff check
make format   # ruff format
make test     # pytest
```
