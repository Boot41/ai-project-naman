# Spec Agent 5: Tools and Retrieval Contracts

## Purpose

Define allowed tooling and retrieval behavior for OpsCopilot.

## Tool Envelope

Tools return contract envelope from `ops-agent/app/tools/contracts.py`.

## Allowed Tools (Only)

- `get_incident_by_key`
- `get_incident_services`
- `get_incident_evidence`
- `get_service_owner`
- `get_service_dependencies`
- `get_similar_incidents`
- `get_resolutions`
- `get_escalation_contacts`
- `load_session_messages`
- `search_docs(query)`

No additional tool names should be introduced in prompts or execution plans.

## Implementation Mapping

- DB/doc/session tools: `ops-agent/app/tools/agent_tools.py`
- Docs ranking/search: `ops-agent/app/tools/docs_search.py`
- Resource index: `ops-agent/resources/index.json`

## Retrieval Flow

- Orchestrator creates tool plan
- Pipeline executes retrieval in parallel
- Results are merged in `ops-agent/app/investigation_flow.py`

## Acceptance Criteria

- Tool names in plans match implementation exactly
- No-data cases return structured no-data payloads
- Retrieval output is safe for context-builder consumption
