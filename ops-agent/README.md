# Ops Agent (MVP)

Standalone Google ADK service for OpsCopilot flow validation.

## Architecture

- `app/main.py`: FastAPI endpoints
- `app/service.py`: query orchestration
- `app/adk_agent.py`: Google ADK agent runner
- `app/tools/web_search.py`: web search tool + fallback answer formatting

## API

- `GET /health`
- `POST /v1/query`

Request:

```json
{
  "query": "What caused the latest OpenAI outage?",
  "user_id": "42"
}
```

Response:

```json
{
  "answer": "Natural language answer from the agent"
}
```

## Local Run

1. `cd ops-agent`
2. `uv sync`
3. `cp .env.example .env` and set `GOOGLE_API_KEY`
4. `uv run uvicorn app.main:app --reload --port 8010`
