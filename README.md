# Embedding Service

A thin API endpoint between TEI (HuggingFace Text Embeddings Inference) and
its consuming services. Takes a batch of texts, re-batches them within
TEI's own request-size limit, validates the response, and returns one
vector per input text - in order.

Stateless: no database, no storage. A caller (e.g. a RAG backend writing
vectors into pgvector) owns persistence and schema on its own side.

## Pipeline

```
texts (POST /api/v1/embed)
  │
  ▼
Batch              re-batched into groups of at most TEI_CLIENT_BATCH_SIZE
  │                (must stay <= TEI's own --max-client-batch-size, or
  │                 every request in an over-sized batch gets a 413)
  ▼
Embed              each batch sent to TEI's /embed endpoint
  │
  ▼
Validate           one vector per input text, each exactly TEI_EMBEDDING_DIM
  │                long - a mismatch raises rather than returning malformed
  │                output
  ▼
Return             {embeddings: [[...], ...], dimension: N}, same order as input
```

## API

| Endpoint | Purpose |
|---|---|
| `POST /api/v1/embed` | Embeds `texts` (max `EMBED_MAX_TEXTS_PER_REQUEST` items, each up to `EMBED_MAX_TEXT_CHARS` characters) and returns one vector per input text, in order. |

All `/api/v1/...` routes require a JWT bearer token - see [docs/AUTH.md](docs/AUTH.md).

## Project layout

```
app/
  main.py             # Wires everything together with this project's settings/routes
  core/                 # Settings, rate limiter
  api/deps.py            # Shared FastAPI dependency providers (embedding service)
  api/v1/routes/         # embed
  schemas/               # Request/response shapes
  integrations/           # TEIEmbeddingService: batching + response validation

libs/                    # Small, reusable, project-agnostic infra helpers
                          # (logging, metrics, errors, rate limiting, the TEI
                          #  HTTP client itself)
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
- `GET /health` - liveness + TEI connectivity (`degraded`/503 if unreachable)
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
