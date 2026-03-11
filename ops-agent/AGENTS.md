# Ops-Agent Development Guide

This file is the local implementation guide for `ops-agent/`.
Use it as the source of truth for architecture, workflows, and development standards in this folder.

## Goal

Build and maintain the OpsCopilot multi-agent incident investigation runtime using Google ADK and Gemini.

Primary workflow:

`User Query -> OpsCopilotOrchestratorAgent -> Parallel Retrieval -> ContextBuilderAgent -> IncidentAnalysisAgent (loop) -> ResponseComposerAgent -> Structured JSON`

## Tech Stack

- Python 3.12+
- Google ADK
- Gemini model: `gemini-2.5-flash`
- FastAPI for HTTP serving
- Pydantic for contracts/schemas

## Core Runtime Entrypoints

- API endpoint:
  - `POST /v1/investigate` in `app/main.py`
- Service entry:
  - `app/service.py::investigate(...)`
- Orchestration runtime:
  - `app/orchestration/pipeline.py::run_investigation_pipeline(...)`
- CLI workflow runner:
  - `run_agent.py`

## Agent Definitions (ADK)

Flat agent files (single-folder layout):

- `app/agents/orchestrator_agent.py`
  - `build_orchestrator_agent()`
  - `orchestrate_with_adk_or_fallback(...)`
- `app/agents/context_builder_agent.py`
  - `build_context_builder_agent()`
  - `context_builder_with_adk_or_fallback(...)`
- `app/agents/incident_analysis_agent.py`
  - `build_incident_analysis_agent()`
  - `analysis_with_adk_or_fallback(...)`
- `app/agents/response_composer_agent.py`
  - `build_response_composer_agent()`
  - `composer_with_adk_or_fallback(...)`
- `app/agents/opscopilot_agent.py`
  - `run_opscopilot_pipeline(...)`
  - `root_agent`

ADK execution helper:

- `app/agents/runtime.py`
  - `build_stage_agent(...)`
  - `run_json_stage(...)`

## Prompt Source

System prompts are inline constants in each `app/agents/*_agent.py` file.

Prompt update rules:

- Keep prompts strict about JSON-only output.
- Do not request markdown output in agent prompts.
- Keep agent role boundaries clear (no cross-role leakage).

## Tooling Layer

Tool contracts and envelope:

- `app/tools/contracts.py`

Database tool exports:

- `app/tools/database_tools.py`

ADK tool wrappers:

- `app/tools/agent_tools.py`

Docs retrieval tool:

- `app/tools/docs_search.py`

Parallel retrieval fan-out/fan-in:

- `app/orchestration/retrieval.py`

## Contracts and Schemas

Agent contracts are centralized in:

- `app/contracts/orchestrator.py`
- `app/contracts/context_builder.py`
- `app/contracts/incident_analysis.py`
- `app/contracts/response_composer.py`

API schemas:

- `app/schemas.py`

All cross-stage payloads should be validated with these models.

## Error Handling and Logging

Pipeline errors:

- `app/orchestration/errors.py`

Pipeline step logging schema:

- `app/orchestration/logging.py`

Persistence gateway (in-memory implementation):

- `app/orchestration/persistence.py`

## Directory Map

- `app/agents/`: stage logic, inline prompts, ADK builders/wrappers, shared runtime helper
- `app/contracts/`: Pydantic contracts per stage
- `app/orchestration/`: pipeline runtime and control plane
- `app/tools/`: tool contracts and retrieval tools
- `tests/unit/`: unit + integration-style pipeline tests
- `resources/`: local docs corpus for `search_docs`

## Development Commands

Setup:

```bash
cd ops-agent
uv sync
```

Run API:

```bash
uv run uvicorn app.main:app --reload --port 8010
```

Run CLI workflow:

```bash
uv run python run_agent.py "Why did incident INC-104 happen?" --user-id 1 --incident-key INC-104
```

Run tests:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python -m unittest
```

Format code (required):

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run ruff format .
```

## Coding Rules

- Keep stage boundaries strict:
  - Orchestrator plans
  - ContextBuilder compresses
  - IncidentAnalysis reasons
  - ResponseComposer formats final output
- Preserve structured JSON contracts; avoid ad-hoc dict shapes.
- Keep retrieval parallel in `RetrievalExecutor`.
- Do not bypass schema validation in stage boundaries.

## Change Checklist

Before finishing changes in this folder:

1. Ensure inline prompts and contracts remain aligned.
2. Ensure tool names in ADK agent registration match retrieval/executor names.
3. Ensure pipeline still returns structured JSON with `status` + `output|error`.
4. Run `ruff format`.
5. Run relevant unit tests.

## Notes for Future Development

- Replace DB tool stubs in `app/tools/agent_tools.py` with real DB-backed implementations.
- Add production persistence adapter for `save_assistant_message` and evidence audit rows.
- Expand observability fields for eval workflows (token usage, model latency, confidence trace).
- Keep backward compatibility of response schema used by backend chat persistence.
