---

# `.claude/skills/fastapi/SKILL.md`

```markdown
---

name: fastapi
description: Use when implementing or reviewing FastAPI endpoints, dependencies, middleware, request validation, SSE, or API behavior.

---

# FastAPI Development

## Routes

Route handlers should:

1. validate input
2. resolve dependencies
3. call application services
4. convert results to API responses

Do not put business logic in route handlers.

Do not put database queries directly in route handlers.

Do not call LLMs or embedding providers directly from route handlers.

## Schemas

- Use Pydantic request models.
- Use explicit response models.
- Do not expose ORM/database models directly.
- Do not accept arbitrary dictionaries when a strict schema is appropriate.
- Add bounds to user-controlled numeric values.
- Add maximum lengths to unbounded user-controlled strings.
