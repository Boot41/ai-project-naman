# Spec Agent 6: End-to-End Runtime, ADK Orchestration, Error Handling, and Implementation Plan

## 1. Purpose

Define complete runtime orchestration using Google ADK from user query to persisted response.

## 2. End-to-End Execution Graph

```text
User Query
  -> OpsCopilotOrchestratorAgent
  -> Parallel Retrieval (DB tools + Docs tool + session history)
  -> ContextBuilderAgent (mandatory context_content)
  -> IncidentAnalysisAgent (loop with policy)
  -> ResponseComposerAgent
  -> save_assistant_message
```

## 3. ADK Node Sequencing

1. Orchestrator node
2. Retrieval fan-out node
3. Retrieval merge node
4. ContextBuilder node
5. Analysis loop node
6. Composer node
7. Persistence node

## 4. Runtime Controls

- Global request timeout: 90s.
- Analysis loop policy from spec-agent-3.
- Abort pipeline on unrecoverable tool errors.
- Recoverable retrieval errors allowed if minimum evidence threshold satisfied.

Minimum evidence threshold for analysis:

- At least one of:
  - incident + evidence
  - service dependencies + docs
  - historical incidents + resolutions

## 5. Error Handling Contract

Standard error payload:

```json
{
  "status": "error|not_found|inconclusive",
  "error_code": "string",
  "message": "string",
  "next_action": "string"
}
```

Error code suggestions:

- `INCIDENT_NOT_FOUND`
- `SERVICE_NOT_FOUND`
- `RETRIEVAL_TIMEOUT`
- `TOOL_EXECUTION_FAILED`
- `INSUFFICIENT_EVIDENCE`
- `SCHEMA_VALIDATION_FAILED`

## 6. Observability and Eval-Ready Logging

Required fields for every agent step:

- `trace_id`
- `request_id`
- `session_id`
- `user_id`
- `agent`
- `step`
- `status`
- `latency_ms`
- `input_tokens`
- `output_tokens`
- `confidence`
- `evidence_refs`

Eval metrics to compute later:

- response schema validity rate
- evidence-groundedness rate
- hypothesis confidence calibration
- retrieval precision@k
- end-to-end latency p50/p95

## 7. Persistence and Session Memory

- Save final response in `messages` table.
- Save evidence references in `investigation_evidence` for auditability.
- Update `sessions.last_activity_at` at end of run.

## 8. Implementation Order

1. Implement tools and schema validation layer.
2. Implement orchestrator routing and tool planning.
3. Implement parallel retrieval fan-out/fan-in.
4. Implement context builder compression.
5. Implement analysis loop and policy guards.
6. Implement response composer and persistence.
7. Add structured logging.
8. Add unit/integration tests.

## 9. Test Plan

Unit tests:

- routing classification
- tool contract validation
- context compression rules
- loop stop/continue decisions
- final output schema validation

Integration tests:

- incident investigation flow
- ownership query flow
- comparison query flow
- no-data and timeout behaviors
- persistence validation (`messages.structured_json`)

## 10. Go-Live Acceptance Criteria

- All specs 1-5 contracts pass validation.
- End-to-end pipeline returns deterministic structured output.
- Logging emits required fields.
- Error responses are structured and actionable.
- Integration tests pass for core user journeys.

## 11. Runtime Entrypoints

- CLI full workflow runner: `ops-agent/run_agent.py`
- API endpoint: `POST /v1/investigate` in `ops-agent/app/main.py`
- Pipeline orchestrator: `ops-agent/app/orchestration/pipeline.py`
- ADK agents and runtime (flat layout):
  - `ops-agent/app/agents/orchestrator_agent.py`
  - `ops-agent/app/agents/context_builder_agent.py`
  - `ops-agent/app/agents/incident_analysis_agent.py`
  - `ops-agent/app/agents/response_composer_agent.py`
  - `ops-agent/app/agents/opscopilot_agent.py`
  - `ops-agent/app/agents/runtime.py`
