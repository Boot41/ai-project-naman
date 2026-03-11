# Spec Agent 7: Prompt System Implementation (ADK)

## 1. Purpose

Define how OpsCopilot prompt assets are implemented, versioned, and enforced in runtime for the four Google ADK agents.

This spec converts prompt design into implementation requirements.

## 2. Scope

Applies to these agents:

- OpsCopilotOrchestratorAgent
- ContextBuilderAgent
- IncidentAnalysisAgent
- ResponseComposerAgent

Prompt files are runtime dependencies and must be treated as production artifacts.

## 3. Prompt File Layout

Store prompt files in:

- `ops-agent/app/prompts/orchestrator.md`
- `ops-agent/app/prompts/context_builder.md`
- `ops-agent/app/prompts/incident_analysis.md`
- `ops-agent/app/prompts/response_composer.md`

Prompt loading implementation:

- `ops-agent/app/adk/runner.py::_load_prompt(...)`

## 4. ADK Integration Contract

ADK builder mapping:

- `build_orchestrator_agent()` -> `orchestrator.md`
- `build_context_builder_agent()` -> `context_builder.md`
- `build_incident_analysis_agent()` -> `incident_analysis.md`
- `build_response_composer_agent()` -> `response_composer.md`

Implementation location:

- `ops-agent/app/adk/agents.py`

Runtime execution location:

- `ops-agent/app/adk/runner.py::run_json_stage(...)`
- `ops-agent/app/agents/adk_flow.py`

Model requirement:

- Gemini model must be `gemini-2.5-flash` unless explicitly overridden in env config.

## 5. Prompt Requirements (Global)

All prompts must enforce:

- strict JSON-only output
- no markdown in output
- no fabricated entities or metrics
- explicit insufficient-information handling
- role-bound behavior (no cross-agent role leakage)

All prompts must be deterministic and concise.

## 6. Agent-Specific Prompt Contracts

### 6.1 Orchestrator Prompt Contract

Must instruct model to return `OrchestratorOutput`:

- `investigation_scope`
- `routing_target`
- `tool_plan[]`
- `context_seed`

Must enforce tool-planning behavior only (no root-cause conclusions).

### 6.2 ContextBuilder Prompt Contract

Must instruct model to return `ContextBuilderOutput`:

- normalized raw fields
- compact `context_content`
- bounded list sizes (`important_events <= 15`, `documentation_findings <= 8`)
- `status`

### 6.3 IncidentAnalysis Prompt Contract

Must instruct model to return `IncidentAnalysisOutput`:

- `hypotheses[]`
- `analysis_decision` (`continue|stop|inconclusive`)
- `missing_information[]`
- `confidence`
- `iteration_summaries[]`

Must enforce evidence-backed reasoning (supporting refs required).

### 6.4 ResponseComposer Prompt Contract

Must instruct model to return `ComposerOutput`:

- `summary`
- `hypotheses`
- `similar_incidents`
- `evidence`
- `owners`
- `escalation`
- `recommended_actions`
- `report`
- `status`

## 7. Schema Enforcement Strategy

`run_json_stage(...)` must include:

- input payload JSON
- output schema JSON (`output_model.model_json_schema()`) in the prompt context

After model response:

- parse JSON response
- validate with Pydantic model
- on validation failure, fail stage and allow fallback path

## 8. Fallback Behavior

If ADK execution fails (missing API key, runtime error, invalid JSON):

- fallback to deterministic stage implementation in `app/agents/*.py`
- preserve same input/output contract

Fallback wrappers:

- `orchestrate_with_adk_or_fallback(...)`
- `context_builder_with_adk_or_fallback(...)`
- `analysis_with_adk_or_fallback(...)`
- `composer_with_adk_or_fallback(...)`

## 9. Analysis Loop Behavior

Prompt + runtime must support loop flow:

- `continue` -> request/expect additional data path
- `stop` -> finalize
- `inconclusive` -> finalize with uncertainty

Runtime policy source of truth:

- `LoopRuntimePolicy` in `app/contracts/incident_analysis.py`
- passed through pipeline to analysis stage

## 10. Tool Usage Governance in Prompts

Prompts must reference available tools only:

- `get_incident_by_key`
- `get_incident_services`
- `get_incident_evidence`
- `get_service_owner`
- `get_service_dependencies`
- `get_similar_incidents`
- `get_resolutions`
- `get_escalation_contacts`
- `load_session_messages`
- `save_assistant_message`
- `search_docs`

Do not mention non-existent tools.

## 11. Prompt Versioning and Change Control

Each prompt file should include a header comment block with:

- `agent_name`
- `version`
- `last_updated`
- `owner`

Any schema or prompt behavior change must update:

- relevant prompt file
- corresponding contract model
- spec docs affected

## 12. Testing Requirements

Required checks for prompt-system changes:

- ADK stage returns parseable JSON
- JSON validates against expected output model
- fallback path works when ADK fails
- no prompt references missing tools

Recommended regression coverage:

- one golden input per agent with schema-valid output
- one malformed-output case to verify fallback

## 13. Acceptance Criteria

- All four agents load prompts from `app/prompts/`.
- All ADK stages use schema-constrained JSON output.
- Prompt-to-contract mapping is one-to-one and documented.
- Pipeline executes with ADK when available and deterministic fallback otherwise.
- No prompt includes ambiguous or non-operational instructions.
