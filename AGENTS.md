# OpsCopilot Investigation Agent

## Project Goal
Build an OpsCopilot AI system that assists operations engineers in investigating incidents.

The system must reason across multiple data sources and provide evidence-backed investigation support through natural language interaction.

## Repository Folders

- `client/`: React/Vite frontend UI and API client integration
- `server/`: FastAPI backend, auth, business services, DB models/migrations
- `ops-agent/`: Google ADK multi-agent investigation runtime (OpsCopilot orchestrator + stage agents + tools + docs resources)

## Backend Architecture

- Data models in `server/app/db/models.py`
- AsyncSession is scoped to HTTP request via `server/app/api/deps.py`
- APIs perform validation and call services (forbidden from calling DB directly)
- Services have business logic, validations and read/write to database
- Authentication via `server/app/auth/deps.py` (`require_user` dependency)

## Authentication (JWT)

- `POST /api/v1/auth/login` returns a JWT token
- JWT tokens signed with HS256, 7-day expiry
- All `/api/v1/*` routes (except auth) require `Authorization: Bearer <token>` header
- Password hashing via bcrypt
- `/health` is public

## Module Boundaries

- `app.api` depends on `app.services`, `app.auth`, `app.core` only
- `app.services` depends on `app.db`, `app.core` only (must NOT import from `app.api`)
- `app.db` depends on `app.core` only (must NOT import from `app.services` or `app.api`)
- These boundaries are enforced by `import-linter` in CI

## Development Workflow

- Developer starts React/Vite on :5173 and FastAPI on :8000
- Vite proxies API requests to FastAPI
- PostgreSQL runs via Docker Compose on :5434

## Build, Test, and Development Commands

- `docker-compose up -d db`: start PostgreSQL locally
- `cd server && uv sync --all-extras`: install backend dependencies (including dev tools)
- `cd server && uv run alembic upgrade head`: apply DB migrations
- `cd server && uv run uvicorn app.main:app --reload --port 8000`: run API in dev mode
- `cd client && npm install`: install frontend dependencies
- `cd client && npm run dev`: run Vite dev server
- `cd ops-agent && uv sync`: install ops-agent dependencies
- `cd ops-agent && uv run uvicorn app.main:app --reload --port 8010`: run ops-agent API
- `cd ops-agent && uv run adk web adk_app`: run ADK Web for agent graph/manual testing

## Quality Gates

Backend (run from `server/`):
- `uv run ruff format --check .`: code formatting
- `uv run ruff check .`: linting
- `uv run mypy .`: type checking (strict mode)
- `uv run lint-imports`: module boundary validation
- `uv run pytest tests/unit -q`: unit tests
- `uv run pytest tests/integration -q`: integration tests

Frontend (run from `client/`):
- `npm run lint`: ESLint
- `npm run build`: TypeScript check + production build

Ops-Agent (run from `ops-agent/`):
- `uv run ruff check .`: linting
- `uv run pytest -q`: tests

## Coding Style

- Python: 4-space indentation, type hints on public functions, `snake_case` for modules/functions, `PascalCase` for classes
- Respect Ruff config in `server/pyproject.toml` (line length 100, import sorting enabled)
- TypeScript/React: `PascalCase` component files, `camelCase` utilities, hooks prefixed with `use`
- Keep backend layering intact: Routes -> Services -> DB

## Testing Guidelines

- Backend: `pytest` + `pytest-asyncio` + `httpx`
- Unit tests in `server/tests/unit/`, integration tests in `server/tests/integration/`
- Use `test_*.py` naming
- Add tests for new endpoints, auth checks, and service-layer edge cases

## Commit & PR Guidelines

- Conventional Commits style (e.g. `feat:`, `fix:`, `refactor:`)
- Keep commits focused and atomic; include migration files with schema changes
- PRs must pass all quality gates in CI before merging
