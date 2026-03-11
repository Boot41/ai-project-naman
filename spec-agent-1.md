# Spec Agent 1: OpsCopilotOrchestratorAgent

## 1. Purpose

OpsCopilotOrchestratorAgent is the entry point for every user request.
It classifies intent, determines investigation scope, creates a deterministic tool plan,
and routes execution to downstream agents.

This agent does not perform root-cause reasoning. It performs planning and routing.

## 2. Responsibilities

- Parse user query and session context.
- Detect whether query is incident-centric, service-centric, ownership/escalation, historical comparison, or report generation.
- Build `tool_plan[]` with explicit tool args.
- Enforce deterministic routing order.
- Initialize canonical `InvestigationContext`.

## 3. Dependencies

- Tools:
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
- Input context:
  - user query
  - session id
  - authenticated user id
  - optional incident key

## 4. Input Contract

```json
{
  "request_id": "string",
  "session_id": "uuid",
  "user_id": 123,
  "query": "string",
  "incident_key": "string|null",
  "service_name": "string|null",
  "session_metadata": {
    "timezone": "string|null",
    "locale": "string|null"
  }
}
```

Validation:

- `query` must be non-empty.
- If provided, `incident_key` must match `^INC-[0-9]+$`.
- `session_id` must be valid UUID.

## 5. Output Contract

```json
{
  "investigation_scope": "incident|service|ownership|comparison|report",
  "routing_target": "context_builder|incident_analysis|response_composer",
  "tool_plan": [
    {
      "tool": "string",
      "args": {},
      "priority": "high|medium|low",
      "reason": "string"
    }
  ],
  "context_seed": {
    "request_id": "string",
    "session_id": "uuid",
    "user_id": 123,
    "query": "string",
    "incident_key": "string|null",
    "service_name": "string|null",
    "status": "in_progress"
  }
}
```

## 6. Query Classification Rules

- `incident`: query includes incident key or incident language (`incident`, `outage`, `root cause`, `what happened`).
- `service`: query asks service health/dependencies without incident key.
- `ownership`: query asks owner/on-call/escalation.
- `comparison`: query asks similar past incidents.
- `report`: query asks full report/exported summary.

If multiple intents are detected, choose highest-priority scope:
`incident > report > comparison > ownership > service`.

## 7. Tool Planning Rules

### Incident scope

Required tools:

- `get_incident_by_key`
- `get_incident_services`
- `get_incident_evidence`
- `load_session_messages`

Conditional tools:

- `get_service_dependencies` for each impacted service
- `get_service_owner` for each impacted service
- `get_escalation_contacts` for each impacted service
- `get_similar_incidents`
- `get_resolutions`
- `search_docs` with category `runbooks`, `postmortems`, `policies`, `architecture`

### Ownership scope

Required tools:

- `get_service_owner`
- `get_escalation_contacts`
- `load_session_messages`

### Service scope

Required tools:

- `get_service_dependencies`
- `get_service_owner`
- `search_docs`
- `load_session_messages`

### Comparison scope

Required tools:

- `get_similar_incidents`
- `get_resolutions`
- `search_docs` (postmortems)
- `load_session_messages`

### Report scope

Required tools:

- all incident scope tools
- all ownership tools
- all comparison tools

## 8. ADK Implementation Notes

- Implement as the first ADK agent node in graph/pipeline.
- Use deterministic system prompt and low temperature.
- Route by explicit rules before allowing free-form LLM interpretation.
- Emit structured JSON only.

Implementation mapping:

- Agent builder + prompt + fallback wrapper: `ops-agent/app/agents/orchestrator_agent.py`
  - `build_orchestrator_agent`
  - `orchestrate_with_adk_or_fallback`
- Shared ADK stage runner: `ops-agent/app/agents/runtime.py` (`run_json_stage`)

## 9. Prompt Template (System)

"You are OpsCopilotOrchestratorAgent. Classify intent, produce deterministic routing, and generate a tool plan with args. Do not infer missing facts as true. If uncertain, request additional retrieval through tool_plan. Output strict JSON only."

## 10. Failure Handling

- If required key data missing (no incident key for incident query), set scope to `incident` and request follow-up via tool-free clarifying response path.
- If tool planning fails, return `status=error` with `error_code=ORCHESTRATOR_PLAN_FAILED`.

## 11. Logging Events

Emit one log entry:

```json
{
  "trace_id": "string",
  "agent": "OpsCopilotOrchestratorAgent",
  "scope": "incident|service|ownership|comparison|report",
  "routing_target": "string",
  "tool_count": 0,
  "latency_ms": 0,
  "status": "success|error"
}
```

## 12. Acceptance Criteria

- Correctly classifies scope for canonical query sets.
- Always emits valid JSON matching output contract.
- Produces deterministic `tool_plan` for same input.
- Never emits root-cause conclusions.
