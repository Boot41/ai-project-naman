# Spec Agent 1: OpsCopilotOrchestratorAgent

## Purpose

Root planning agent for OpsCopilot. It classifies the user request, builds retrieval plan, and routes to ContextBuilder.

## Runtime Mapping

- File: `ops-agent/app/agents/orchestrator_agent.py`
- Stage function: `orchestrate_with_adk_or_fallback(...)`
- Root ADK entry: `root_agent`
- Tool wrapper exposed to ADK: `run_opscopilot_pipeline(...)`

## Input Contract

`OrchestratorInput` from `ops-agent/app/contracts/orchestrator.py`.

## Output Contract

`OrchestratorOutput` from `ops-agent/app/contracts/orchestrator.py`.

Required behavior:

- JSON only
- no root-cause reasoning
- no hallucinated facts
- if uncertain, still output valid tool plan

## Allowed Tools for Planning

- `get_incident_by_key`
- `get_incident_services`
- `get_incident_evidence`
- `get_service_owner`
- `get_service_dependencies`
- `get_similar_incidents`
- `get_resolutions`
- `get_escalation_contacts`
- `load_session_messages`
- `search_docs`

## Scope Priority

`incident > report > comparison > ownership > service`

## Acceptance Criteria

- Always returns valid `OrchestratorOutput`
- Produces deterministic tool plan for same input
- Routes to `context_builder`
