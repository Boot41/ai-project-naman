# Pure ADK Agent-to-Agent Migration Plan

## Goal
Switch OpsCopilot runtime from custom pipeline orchestration to pure Google ADK multi-agent communication, while keeping:
- API flow working (`/v1/investigate`)
- ADK Web flow working (`adk web adk_app`)
- Existing response contract stable for server/client integration

## Current State (Summary)
- API path currently delegates to `run_investigation_pipeline(...)` (deterministic custom orchestration).
- ADK Web exposes `root_agent` graph.
- Stage agents exist (`orchestrator`, `context_builder`, `incident_analysis`, `response_composer`) but runtime coordination is mostly pipeline-driven.

## Target State
- `root_agent` (ADK `SequentialAgent` + loop stage) is the primary runtime for both API and ADK Web.
- Inter-agent data transfer happens through ADK context/messages, not pipeline-assembled typed payloads.
- API returns normalized output in existing schema: `trace_id/status/output/error/logs/persistence`.

## Scope
In scope:
- Runtime migration to ADK-first execution
- Agent contract updates for stage-to-stage communication
- Output normalization adapter for API
- Regression tests for critical scenarios

Out of scope:
- New product features
- UI redesign
- DB schema changes unless strictly required

## Work Plan

## Phase 1: Baseline and Safety Net
1. Freeze current behavior with golden test cases:
   - incident root-cause query
   - ownership/escalation query
   - dependency follow-up query with session memory
   - full report query
2. Capture expected minimal output fields and status semantics.
3. Add temporary feature flag:
   - `OPS_AGENT_RUNTIME_MODE=pipeline|adk`
   - default to `pipeline` during migration.

## Phase 2: ADK Runtime Entry for API
1. Implement API runtime path that executes `root_agent` via ADK `Runner`.
2. Reuse incoming `session_id` and `user_id` so chat memory continuity remains.
3. Create response adapter:
   - parse final ADK output
   - map to `InvestigationResponse` contract fields.

## Phase 3: Agent Contract Refactor
1. Define strict JSON exchange format between stage agents:
   - orchestrator output envelope
   - context-builder output envelope
   - analysis output envelope
   - composer output envelope
2. Update prompts so each stage consumes previous stage payload from context and returns only its schema.
3. Remove hard dependency on pipeline-built typed payload injection.

## Phase 4: Retrieval Strategy in Pure ADK
1. Decide retrieval model:
   - Option A: allow ADK agent to call tools directly as needed.
   - Option B: create one composite tool that performs parallel fan-out and merge.
2. If performance parity is needed, implement composite retrieval tool (parallel internals).
3. Ensure evidence source tagging remains consistent (`db/docs/session`).

## Phase 5: Analysis Loop in ADK
1. Keep analysis iteration in ADK loop stage (current `LoopAgent`).
2. Ensure loop stop criteria are explicit:
   - confidence threshold
   - max iterations
   - no additional useful tool calls.
3. Preserve “inconclusive” behavior when evidence is insufficient.

## Phase 6: Decommission Pipeline Runtime
1. Switch default runtime mode to `adk`.
2. Keep pipeline code for one short deprecation window (optional).
3. Remove pipeline-only runtime path after validation passes.

## Validation Checklist
- API `/v1/investigate` returns valid contract in ADK mode.
- ADK Web graph still runs and shows stage agents.
- Session follow-up queries use same context (`session_id`) across turns.
- Required capabilities verified:
  - incident summary
  - root cause + evidence refs
  - ownership + escalation
  - full report
- Error/inconclusive responses still structured and stable.

## Risks and Mitigations
1. Risk: Output shape drift in pure ADK.
   - Mitigation: strict schema prompts + adapter validation.
2. Risk: Non-deterministic tool usage quality.
   - Mitigation: stronger tool policy prompts and constrained tool descriptions.
3. Risk: Latency increase without pipeline fan-out.
   - Mitigation: composite retrieval tool with internal parallel calls.
4. Risk: Memory mismatch between API and ADK Web sessions.
   - Mitigation: standardized session key handling and integration tests.

## Estimated Effort
- Basic runtime switch + adapter: low to medium
- Clean pure ADK inter-agent contracts: medium
- Quality/performance parity with current pipeline: medium to high

## Deliverables
1. ADK-first API runtime path
2. Updated stage prompts/contracts for agent-to-agent communication
3. Response adapter with contract validation
4. Migration regression tests
5. Final cleanup PR removing pipeline runtime dependency

## Suggested Task Breakdown (PRs)
1. PR-1: Runtime mode flag + API ADK runner path + adapter skeleton
2. PR-2: Stage contract refactor for ADK context handoff
3. PR-3: Retrieval strategy optimization (composite tool if needed)
4. PR-4: Tests, parity fixes, and default switch to ADK mode
5. PR-5: Pipeline runtime deprecation/removal cleanup

## Execution Update (Branch: `agent-pipeline-fix`)
- We are implementing directly on an isolated branch, so no runtime feature flag is required.
- Migration approach for this branch:
  1. Switch API entry runtime to execute ADK `root_agent` directly.
  2. Keep API response envelope stable via adapter mapping.
  3. Validate parity on key prompts/session-memory flows.
  4. Remove pipeline runtime dependency after parity checks.

### Revised Immediate Steps
1. Replace API runtime call path from `run_investigation_pipeline(...)` to ADK `Runner(root_agent, ...)`.
2. Parse final ADK output and normalize to `InvestigationResult` schema.
3. Keep `root_agent` export for ADK Web unchanged.
4. Run targeted regression scenarios and then remove unused pipeline runtime code.

## Implementation Status
- Done: API runtime now executes ADK `root_agent` and normalizes output envelope.
- Done: Agent prompt handoff guidance tightened for orchestrator/context/analysis/composer.
- Done: Added `get_investigation_bundle` composite retrieval tool (parallel internal execution) for lower latency and stable context handoff.
- Done: Runtime result/error models extracted to `app/contracts/investigation_result.py` to reduce pipeline coupling.
- Pending: full regression parity run against golden prompts before deleting `app/investigation_flow.py` file completely.
