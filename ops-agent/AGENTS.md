# Ops-Agent Development Guide

Source of truth for `ops-agent/` implementation.

## Goal

Build and maintain the simplified OpsCopilot ADK flow:

`User Query -> OpsCopilotOrchestratorAgent -> ContextBuilderAgent -> IncidentAnalysisAgent (loop) -> ResponseComposerAgent -> Structured JSON`

## Current Runtime Structure

- API entry: `app/main.py` (`POST /v1/investigate`)
- Service entry: `app/service.py::investigate(...)`
- Shared entry routing: `app/investigation_entry.py::run_investigation_entrypoint(...)`
- ADK runtime entry: `app/agents/orchestrator_agent.py::run_investigation_via_root_agent(...)`
- CLI runner: `run_agent.py`
- ADK web exports:
  - `adk_app/agent.py`

There is no `app/orchestration/` runtime in active flow.

## Agents

- `app/agents/orchestrator_agent.py`
  - root ADK agent (`root_agent`)
  - graph root (`OpsCopilotInvestigationFlow`)
  - tool entry (`run_opscopilot_pipeline`)
  - stage planner (`orchestrate_with_adk_or_fallback`)

API routing note:
- API and ADK Web both execute `root_agent` graph runtime.
- `app/agents/context_builder_agent.py`
- `app/agents/incident_analysis_agent.py`
- `app/agents/response_composer_agent.py`
- `app/agents/runtime.py` (shared ADK stage execution helpers)

Prompts are inline constants in these files.

Prompt/routing behavior:
- Agent-first decision making (planner + stage prompts).
- For docs-guidance queries, orchestrator routes docs retrieval with category hints:
  - `policies`, `runbooks`, `postmortems`, `architecture`.
- For policy/architecture docs retrieval, bundle search avoids over-filtering by `service`.

## Model

- Default model: `gemini-2.5-flash`
- Config location: `app/core/config.py`
- Env override: `MODEL_NAME`

## Allowed Tools

Only these tools are in scope:

- `get_incident_by_key`
- `get_investigation_bundle`
- `get_incident_services`
- `get_incident_evidence`
- `get_service_owner`
- `get_service_dependencies`
- `get_similar_incidents`
- `get_resolutions`
- `get_escalation_contacts`
- `load_session_messages`
- `search_docs`

Tool implementations:

- `app/tools/agent_tools.py`
- `app/tools/docs_search.py`
- `app/tools/contracts.py`

Docs source of truth:
- `resources/index.json`
- `resources/runbooks/*`
- `resources/postmortems/*`
- `resources/policies/*`
- `resources/architecture/*`

## Contracts

- `app/contracts/orchestrator.py`
- `app/contracts/context_builder.py`
- `app/contracts/incident_analysis.py`
- `app/contracts/response_composer.py`
- `app/contracts/investigation_result.py`
- `app/schemas.py`

All stage I/O must validate against contracts.

## Persistence Ownership

- `ops-agent` returns structured response payload.
- Backend `server` owns DB persistence of assistant output.
- Do not add persistence side-effects inside `ops-agent` investigation runtime.

## Commands

```bash
cd ops-agent
uv sync
uv run uvicorn app.main:app --reload --port 8010
uv run python run_agent.py "Summarize incident INC-2026-0001." --user-id 1
uv run adk web adk_app
```

Note:
- `ruff`/`mypy` are not currently declared in `ops-agent/pyproject.toml`; add them before enforcing local lint/typecheck commands in this package.

## Change Checklist

1. Keep flow and stage order unchanged.
2. Keep tool set restricted to allowed list above.
3. Keep JSON contracts strict; no free-form outputs between stages.
4. Keep insufficient-data behavior explicit: `"we don't have knowledge about this"` / `"insufficient information"`.
5. Keep docs answers evidence-backed from `resources` corpus (policy/runbook/postmortem/architecture).
