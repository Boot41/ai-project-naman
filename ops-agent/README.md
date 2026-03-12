# Ops Agent (MVP)

Standalone Google ADK service for OpsCopilot flow validation.

## Architecture

- `app/main.py`: FastAPI endpoints
- `app/service.py`: service entrypoints
- `app/investigation_entry.py`: shared external investigation entry
- `app/agents/orchestrator_agent.py`: ADK root runtime + API adapter
- `app/agents/`: 4-stage agent logic + ADK roots
- `app/contracts/`: stage and API contracts
- `app/tools/`: tool contracts, docs search, tool registry
- `adk_app/`: ADK web agent exports

## API

- `GET /health`
- `POST /v1/investigate`

Request:

```json
{
  "request_id": "req-123",
  "session_id": "11111111-1111-1111-1111-111111111111",
  "user_id": 42,
  "query": "Why did incident INC-2026-0001 happen?",
  "incident_key": "INC-2026-0001",
  "service_name": "payment-service"
}
```

Response:

```json
{
  "trace_id": "...",
  "status": "complete",
  "output": {
    "summary": "...",
    "hypotheses": [],
    "similar_incidents": [],
    "evidence": [],
    "owners": [],
    "escalation": [],
    "recommended_actions": [],
    "report": "...",
    "status": "complete"
  },
  "error": null
}
```

## Workflow

`User Query -> OpsCopilotOrchestratorAgent -> ContextBuilderAgent -> IncidentAnalysisAgent (loop) -> ResponseComposerAgent -> Structured JSON`

Docs-guidance routing:
- Policy/runbook/postmortem/architecture queries are routed to local docs retrieval from `resources/`.
- Responses are expected to include evidence refs from docs (for example `doc:incident_response_policy`).

## Local Run

1. `cd ops-agent`
2. `uv sync`
3. `cp .env.example .env` and set `GOOGLE_API_KEY`
4. `uv run uvicorn app.main:app --reload --port 8010`

Execution note:
- API `/v1/investigate` executes ADK `root_agent` runtime via `run_investigation_via_root_agent`.
- ADK Web uses the same graph-visible `root_agent` export from `adk_app/agent.py`.
- Both paths now run through the same ADK stage-graph behavior.
- Tool/data fallback behavior:
  - DB-first for incident/service data tools.
  - Seed fallback from `server/seed_data` when DB is unavailable.
  - Docs retrieval from `ops-agent/resources` index and markdown corpus.

## ADK Web Run (Manual Testing)

`ops-agent` includes an ADK-web agents directory at `adk_app/` with one
top-level export: `agent.py`.

```bash
cd ops-agent
UV_CACHE_DIR=/tmp/uv-cache uv sync
UV_CACHE_DIR=/tmp/uv-cache uv run adk web adk_app
```

Notes:
- In the ADK selector, choose the single app exported from `adk_app`.
- This uses Gemini model `gemini-2.5-flash` from your `app/core/config.py`.
- Ensure `GOOGLE_API_KEY` is set in `ops-agent/.env` before launching.

## CLI Run

```bash
cd ops-agent
uv run python run_agent.py "Why did incident INC-2026-0001 happen?" --user-id 1 --incident-key INC-2026-0001
```
