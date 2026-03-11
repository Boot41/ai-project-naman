# Spec Agent 6: End-to-End Runtime and Error Handling

## Purpose

Define the implemented end-to-end investigation runtime.

## Active Flow

`User Query -> OpsCopilotOrchestratorAgent -> Parallel Retrieval -> ContextBuilderAgent -> IncidentAnalysisAgent (loop) -> ResponseComposerAgent -> Final Structured Response`

Runtime file:

- `ops-agent/app/investigation_flow.py`

## Entrypoints

- API: `POST /v1/investigate` in `ops-agent/app/main.py`
- Service: `ops-agent/app/service.py`
- CLI: `ops-agent/run_agent.py`
- ADK Web export: `ops-agent/adk_app/opscopilot/agent.py`

## Runtime Policy

- global pipeline timeout from `PipelineRuntimePolicy`
- stage-level ADK calls with bounded timeout
- structured fallback path when ADK stage fails

## Error Payload

Returned in `InvestigationResult.error` with fields:

- `status`
- `error_code`
- `message`
- `next_action`

Current error code set is defined in `PipelineErrorCode`.

## Persistence Boundary

- `ops-agent` returns response and logs
- backend `server` owns saving assistant message to DB

## Acceptance Criteria

- Flow order is preserved
- Output is always structured (`output` or `error`)
- No hidden free-form failure responses
