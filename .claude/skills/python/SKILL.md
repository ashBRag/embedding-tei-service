---
name: python
description: Use when implementing, refactoring, or reviewing Python code.
---

# Python Development

## Before changing code

- Read the relevant `pyproject.toml`.
- Identify the configured Python version.
- Identify Ruff and type-checker configuration.
- Follow existing package structure.
- Check nearby tests before changing behavior.

## Implementation

- Add type hints to public interfaces.
- Prefer small functions with one responsibility.
- Prefer composition over inheritance.
- Use `Protocol` for replaceable infrastructure interfaces.
- Keep I/O at explicit boundaries.
- Do not hide network or database calls inside generic utility functions.
- Do not introduce a new abstraction unless it represents a real boundary or is reused.

## Async

- Do not perform blocking I/O in async functions.
- Use async database and HTTP clients in async request paths.
- Use `asyncio.sleep()` instead of `time.sleep()` in async code.
- Preserve cancellation behavior.
- Do not catch `CancelledError` and suppress it.

## Exceptions

- Catch exceptions only when handling or translating them.
- Preserve causes when wrapping exceptions.
- Do not return `None` or an empty result to hide an operational failure.
- Use domain-specific exceptions at library boundaries.

## Dependencies

- Check existing dependencies before adding one.
- Update the lockfile after dependency changes.
- Do not introduce duplicate libraries providing the same functionality.

## Verification

Run the repository's configured:

```text
ruff check
ruff format --check
pytest
type checker
```
