# Spec Agent 7: Prompt and ADK Stage Execution

## Purpose

Define prompt and ADK execution rules for simplified OpsCopilot agents.

## Prompt Location

Prompts are inline constants in:

- `ops-agent/app/agents/orchestrator_agent.py`
- `ops-agent/app/agents/context_builder_agent.py`
- `ops-agent/app/agents/incident_analysis_agent.py`
- `ops-agent/app/agents/response_composer_agent.py`

There is no separate `app/prompts/` dependency in the current implementation.

## ADK Stage Runner

- Shared runner: `ops-agent/app/agents/runtime.py`
- Stage execution: `run_json_stage(...)` and `run_json_stage_with_timeout(...)`

## Prompt Requirements

All stage prompts must enforce:

- strict JSON output
- evidence-grounded responses
- insufficient information handling
- no hallucinated entities/metrics

## Model Requirement

- default model is `gemini-2.5-flash`
- source of truth: `ops-agent/app/core/config.py`
- env override supported via `MODEL_NAME`

## Tool Governance in Prompts

Prompts must reference only approved tool list from `spec-agent-5.md`.

## Acceptance Criteria

- Each stage returns schema-valid JSON
- Prompt behavior aligns with contract models
- ADK failures cleanly fall back to deterministic stage outputs
