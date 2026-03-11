# Spec Agent 4: ResponseComposerAgent

## Purpose

Builds final user-facing structured JSON response.

## Runtime Mapping

- File: `ops-agent/app/agents/response_composer_agent.py`
- Stage function: `composer_with_adk_or_fallback(...)`

## Input Contract

`ComposerInput` from `ops-agent/app/contracts/response_composer.py`.

## Output Contract

`ComposerOutput` from `ops-agent/app/contracts/response_composer.py`.

Response must include:

- `summary`
- `hypotheses`
- `similar_incidents`
- `evidence`
- `owners`
- `escalation`
- `recommended_actions`
- `report`
- `status`

## Behavior Rules

- JSON only
- if data gaps exist, explicitly state insufficient information
- no fabricated references

## Persistence Note

`ops-agent` does not persist final messages. Persistence is handled by backend `server`.

## Acceptance Criteria

- Always returns contract-valid structured output
- Output remains grounded in retrieved evidence/context
