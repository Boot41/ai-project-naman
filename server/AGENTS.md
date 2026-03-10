# Server AGENTS Guide

This file is a fast-reference map for the backend in `server/`.
Use it to quickly find where to implement features, debug issues, and run checks.

## 1. Backend Stack
- Framework: FastAPI
- ORM: SQLAlchemy 2.0 async
- Migrations: Alembic
- Auth: JWT (HS256) + refresh tokens
- DB: PostgreSQL (dev), SQLite possible for some local test runs

## 2. Layering Rules (Must Follow)
- Routes (`app/api/routes`) handle HTTP only.
- Services (`app/services`) contain business logic.
- DB models (`app/db/models.py`) contain schema definitions.
- Routes must not contain business logic.
- Services must not import from `app.api`.
- DB must not import from `app.services` or `app.api`.

## 3. Project Map
- App entry: `app/main.py`
- Root router: `app/api/router.py`
- Route modules: `app/api/routes/`
- Auth deps: `app/auth/deps.py`
- Service layer: `app/services/`
- DB models: `app/db/models.py`
- DB session/engine: `app/db/session.py`
- Migrations: `alembic/versions/`
- Settings: `app/core/config.py`

## 4. Current API Surface
Public:
- `GET /health`
- `POST /auth/login`
- `POST /auth/refresh`
- `POST /auth/logout`

Protected (`/api/v1/*`):
- `POST /api/v1/agent/run`
- `GET /api/v1/chat/sessions`
- `POST /api/v1/chat/sessions`
- `DELETE /api/v1/chat/sessions/{session_id}`
- `GET /api/v1/chat/sessions/{session_id}/messages`
- `POST /api/v1/chat/sessions/{session_id}/messages`

## 5. Auth Essentials
- Access token TTL: 15 minutes
- Refresh token TTL: 7 days
- Allowed app role: `operations_engineer`
- `require_user` validates token and user status/role
- `current_user` reads the authenticated user from request state

## 6. DB Schema Essentials (MVP)
Core tables:
- `users`
- `services`
- `service_dependencies`
- `incidents`
- `incident_services`
- `incident_tags`
- `incident_evidence`
- `resolutions`
- `escalation_contacts`
- `sessions`
- `messages`
- `investigation_evidence`
- `refresh_tokens`

Chat model:
- `sessions` stores conversation containers (chat-only mode)
- `messages` stores user/assistant/system messages
- `messages.structured_json` stores assistant structured output payloads

## 7. Chat Behavior Essentials
- Session creation defaults to `session_type = "chat"`
- Hard delete removes session and all messages
- Sending a message persists:
  1. user message
  2. assistant message
- Session title logic:
  - If title is empty or `New Investigation`, set from first user message
  - Normalize whitespace
  - Max length 48 chars
  - Fallback: `New Investigation`

## 8. Implementation Workflow
1. Update/extend models in `app/db/models.py` if schema changes.
2. Add/update migration in `alembic/versions/`.
3. Implement business logic in `app/services/`.
4. Keep route handlers thin in `app/api/routes/`.
5. Add tests in `tests/unit/` and `tests/integration/`.
6. Run all quality gates.

## 9. Quality Gates (Run From `server/`)
- `uv run ruff check .`
- `uv run mypy app`
- `UV_CACHE_DIR=/tmp/uv-cache uv run lint-imports`
- `uv run pytest tests/unit -q`
- `uv run pytest tests/integration -q`

## 10. Gotchas
- Keep route files free of business logic.
- Keep role checks centralized in auth/service logic.
- If external model provider is missing, chat assistant may fallback to a safe default response.
- Integration tests may require a valid DB setup depending on local environment.
