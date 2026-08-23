# Project Rules

## Runtime

- Use the Python version declared in `pyproject.toml`.
- Use `uv` for dependency management when `uv.lock` is present.
- Do not modify dependency versions unless required by the task.
- Do not add dependencies when an existing dependency already provides the required functionality.

## Code Quality

- Use Ruff for formatting, linting, and import sorting.
- Run the configured test suite after code changes.
- Run the configured type checker when present.
- Add or update tests for changed behavior.
- Do not modify unrelated files.
- Do not introduce unused imports, variables, functions, or dependencies.
- Do not use wildcard imports.
- Do not use `eval()` or `exec()`.
- Do not use bare `except:` blocks.
- Do not silently swallow exceptions.

## Python

- Add type hints to public functions, methods, and class attributes.
- Do not use mutable default arguments.
- Use `pathlib.Path` for filesystem paths.
- Use timezone-aware datetimes.
- Do not perform blocking I/O inside async code.
- Use async clients for async HTTP and database operations.
- Do not use `requests` or `time.sleep()` inside async request paths.

## Package Boundaries

- Application packages may import library packages.
- Library packages must not import application packages.
- Core library code must not import FastAPI.
- Core library code must not import provider SDKs.
- Provider-specific implementations must remain in integration/provider modules.
- Do not use `sys.path` manipulation to bypass package boundaries.
- Do not create circular dependencies.

## Configuration

- Do not hard-code secrets or credentials.
- Do not commit `.env` files containing secrets.
- Do not read environment variables throughout business logic.
- Centralize runtime configuration.
- Do not hard-code environment-specific URLs, model names, credentials, or feature flags.

## API

- Keep FastAPI route handlers thin.
- Do not put database queries, LLM calls, embedding calls, or document-processing pipelines directly in route handlers.
- Use explicit Pydantic request and response models.
- Do not expose database models directly as API responses.
- Do not expose provider SDK objects directly from API endpoints.
- Do not expose internal stack traces or provider errors to clients.
- Apply authentication and authorization before accessing protected resources.
- Apply server-side limits to request sizes, pagination, uploads, retrieval counts, and generation limits.

## Async Streaming

- Keep HTTP/SSE transport code in the API layer.
- Do not import FastAPI SSE types into core libraries.
- Represent internal streaming output as application events.
- Do not buffer complete LLM responses before sending streamed responses.
- Handle client disconnects where supported.
- Do not log individual generated tokens.

## RAG

- Keep document loading, parsing, chunking, masking, embedding, retrieval, context construction, and generation as separate components.
- Keep provider implementations behind interfaces.
- Preserve document and chunk provenance through retrieval.
- Do not retrieve unrestricted tenant data and filter it after retrieval.
- Apply authorization before including documents in LLM context.
- Apply configured masking before sending sensitive content to external models.
- Enforce context and token limits.
- Do not use an LLM to make authorization decisions.

## Security

- Never log API keys, passwords, tokens, cookies, authorization headers, or private keys.
- Never return secrets through API responses.
- Do not trust client-supplied `user_id`, `tenant_id`, `owner_id`, roles, or permissions for authorization.
- Do not construct SQL using string concatenation.
- Do not pass untrusted input to shell commands.
- Do not use unsafe deserialization for untrusted input.
- Validate user-controlled URLs before making outbound requests.
- Protect URL fetching against SSRF.
- Validate uploaded files and enforce size limits.
- Protect filesystem operations against path traversal.
- Treat retrieved documents as untrusted input.
- Protect against prompt injection.
- Enforce tenant isolation at the database/query layer where applicable.
- Add security tests for security-sensitive changes.

## Testing

- Unit tests must not require live LLM/provider calls unless explicitly marked as integration tests.
- Unit tests must not use production credentials or production databases.
- Test success and failure paths for new provider integrations.
- Test authorization and cross-tenant access for protected resources.
- Test streaming separately from non-streaming behavior.
- Test masking behavior with both matching and non-matching inputs.
- Do not delete or weaken tests to make a change pass.

## Git

- Do not rewrite git history.
- Do not force-push.
- Do not commit secrets.
- Do not modify generated files unless they are intentionally tracked.
- Do not reformat unrelated files.
