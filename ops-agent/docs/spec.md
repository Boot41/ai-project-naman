# Ops-Agent Implementation Spec (MVP)

## 1. Purpose

`ops-agent` is a standalone service that provides a minimal web-enabled AI answerer for OpsCopilot flow validation.

Primary goal:
- Accept a query from backend.
- Use Google ADK agent (Gemini) with a web-search tool.
- Return a natural-language answer.

Out of scope (current MVP):
- No PostgreSQL usage.
- No incident graph reasoning.
- No long-term memory/state persistence.
- No document retrieval.

## 2. Runtime Architecture

High-level flow:
1. Frontend sends message to backend.
2. Backend calls `ops-agent` (`POST /v1/query`).
3. `ops-agent` runs ADK agent with `web_search` tool.
4. `ops-agent` returns answer to backend.
5. Backend returns answer to frontend.

Service boundaries:
- `client`: UI and chat interactions.
- `server`: auth/session/message persistence + proxy to agent.
- `ops-agent`: LLM + web search execution only.

## 3. Code Structure

Current structure:
- `app/main.py`:
  - FastAPI app and HTTP routes.
  - `GET /health`
  - `POST /v1/query`
- `app/schemas.py`:
  - Request/response Pydantic models.
- `app/service.py`:
  - Orchestration layer (`answer_query`).
  - Fallback strategy if ADK fails.
- `app/adk_agent.py`:
  - Google ADK agent setup and execution.
  - Model selection from config.
- `app/tools/web_search.py`:
  - `web_search` tool implementation (DuckDuckGo Instant Answer API).
  - Fallback answer formatting from tool results.
- `app/core/config.py`:
  - Environment/config loading.

## 4. API Contract

### 4.1 Health

`GET /health`

Response:
```json
{
  "status": "ok"
}
```

### 4.2 Query

`POST /v1/query`

Request:
```json
{
  "query": "What is Newton's third law?",
  "user_id": "42"
}
```

Response:
```json
{
  "answer": "For every action, there is an equal and opposite reaction..."
}
```

Validation:
- `query` is required and must be non-empty.
- `user_id` is optional (defaults to `"backend-user"`).

## 5. Agent Behavior

Execution order in `answer_query`:
1. Try ADK agent path (`run_adk_agent`).
2. If ADK path fails or returns empty text, fallback to direct tool call:
   - Execute `web_search(query)`.
   - Format natural-language answer (`format_web_search_answer`).
3. If tool call also fails, return a safe failure message.

Expected output quality:
- Concise natural language.
- Source URLs included where available.
- Explicit uncertainty when results are weak.

## 6. Web Search Tool

Tool:
- Name: `web_search`
- Backing API: DuckDuckGo Instant Answer API
- URL form:
  - `https://api.duckduckgo.com/?q=<query>&format=json&no_html=1&skip_disambig=1`

Returned tool payload:
- `query`
- `results[]` with:
  - `title`
  - `snippet`
  - `url`

Tool timeout:
- Controlled by `web_search_timeout_seconds` config.
- If unset in environment, default is from code.

## 7. Configuration

Environment is loaded from `ops-agent/.env`.

Config keys:
- `APP_NAME` (optional, default: `ops-agent`)
- `MODEL_NAME` (default: `gemini-2.5-flash`)
- `GOOGLE_API_KEY` (required for ADK Gemini calls)
- `WEB_SEARCH_TIMEOUT_SECONDS` (optional, default from code)

Notes:
- If `GOOGLE_API_KEY` is missing/invalid, ADK path may fail and fallback path is used.

## 8. Error Handling

Error strategy:
- API route does not expose internal stack traces.
- Service-level fallback keeps user response non-empty whenever possible.
- Final failure message is returned only when both ADK and direct search fail.

Current logging:
- Minimal; suitable for MVP.
- Production should add structured logs and request IDs.

## 9. Local Development

Run:
1. `cd ops-agent`
2. `uv sync`
3. Configure `.env` with `GOOGLE_API_KEY`
4. `uv run uvicorn app.main:app --reload --port 8010`

Manual test:
```bash
curl -sS -X POST http://localhost:8010/v1/query \
  -H "Content-Type: application/json" \
  -d '{"query":"What is Newtons third law?","user_id":"local-dev"}'
```

## 10. Backend Integration Contract

Backend caller expectations:
- Calls `POST {OPS_AGENT_BASE_URL}/v1/query`.
- Sends:
  - `query`: user text
  - `user_id`: backend-authenticated user id as string
- Receives:
  - `answer`: final assistant text

Backend should treat non-200 or malformed response as agent failure and return fallback text to frontend.

## 11. Known Limitations

- No streaming token output.
- No citations normalization beyond URLs in plain text.
- No retry/backoff policy for external web API.
- No persisted conversation memory in agent service.
- No per-domain prompt tuning yet.

## 12. Extension Plan

Recommended next steps:
1. Add structured response schema (summary, evidence, actions) from agent service.
2. Add retry/backoff and circuit-breaker for web search/API failures.
3. Add observability: request IDs, latency metrics, failure counters.
4. Add optional domain adapters (fintech/e-commerce/healthcare prompts/tools).
5. Add integration tests with mocked external APIs.

