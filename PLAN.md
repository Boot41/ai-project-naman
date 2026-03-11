# Project Title : OpsCopilot Investigation Agent

Build an OpsCopilot AI system that assists operations engineers in investigating incidents.

## The system must retrieve and analyze information from:
- a local postgres database (incident records, service metadata, metrics snapshots, historical resolutions, contacts)
- local documentation files (runbooks, postmortems, architecture docs, policies)

Users should interact with the system using natural language queries.

## The system should support:
- incident investigation & summary generation
- root cause hypothesis with supporting evidence
- historical incident comparison
- ownership & escalation identification
- contextual conversation (follow-up questions with memory)
- structured JSON outputs
- full incident report generation

The focus of this project is how well the system reasons with multiple data sources rather than simple data retrieval.

---

# OpsCopilot Agent Development Plan

This document describes the agent architecture for the **OpsCopilot AI incident investigation system**.

The goal is to build a **simple but effective agentic workflow using Google ADK** that reasons across multiple data sources:

- PostgreSQL operational database
- Local documentation (Agentic RAG)
- Conversation history

---

# 1. Agentic System Overview

The system uses a **multi-agent architecture** where each agent has a specific responsibility.

Agents perform **reasoning**, while **tools retrieve data**.

The workflow combines **sequential execution, parallel retrieval, and loop-based reasoning** to produce the best response.

---

# 2. High Level Workflow

```text
User Query
↓
OpsCopilotOrchestratorAgent
↓
Parallel Data Retrieval
   ├── DatabaseTools
   └── DocsTools (search_docs)
↓
ContextBuilderAgent
↓
IncidentAnalysisAgent (loop reasoning if needed)
↓
ResponseComposerAgent
↓
Structured JSON Response
```

---

# 3. Execution Strategy

The system uses three execution modes.

## Sequential Execution

Agents run one after another when output from one is required by the next.

Used for:

```text
Orchestrator → ContextBuilder → IncidentAnalysis → ResponseComposer
```

This ensures reasoning occurs on a structured context.

---

## Parallel Execution

Data retrieval tools run in parallel to reduce latency.

Parallel components:

- DatabaseTools
- DocsTools

Example:

- get_incident_by_key
- get_incident_evidence
- search_docs
- load_session_messages

Running these in parallel improves response time.

---

## Loop Execution

The **IncidentAnalysisAgent** may run in a loop when additional information is required.

Example cases:

- missing incident data
- insufficient evidence
- unclear root cause
- conflicting signals

Loop logic:

```text
Analyze context
↓
Check if more evidence is required
↓
Call additional tools
↓
Update context
↓
Repeat reasoning
```

Loop stops when:

- confidence threshold reached
- sufficient evidence collected
- maximum iteration reached

Runtime policy (fixed defaults for implementation):

- `max_iterations = 3` for IncidentAnalysisAgent
- `target_confidence = 0.75` for root-cause hypothesis
- `per_tool_timeout_seconds = 8`
- `per_iteration_budget_seconds = 20`
- `analysis_total_budget_seconds = 60`
- `max_additional_tool_calls_per_iteration = 4`

Loop decision rules:

- Stop early when `best_hypothesis.confidence >= target_confidence` and at least 2 independent evidence items are present.
- Continue loop when confidence is below threshold and at least one unresolved evidence gap exists.
- Stop with `status = inconclusive` when max iterations or time budget is reached.
- Do not call the same tool with identical arguments twice in one iteration.
- Every iteration must append an iteration summary with: requested evidence, received evidence, confidence delta, and stop/continue decision.

---

# 4. Agents

The system uses **four LLM agents**.

---

## 4.1 OpsCopilotOrchestratorAgent

### Role

The **entry point** of the system.

Responsibilities:

- Interpret user intent
- Determine investigation scope
- Decide which tools to call
- Coordinate the workflow
- Trigger parallel data retrieval

## Inputs

- User query
- Session context

## Outputs

- Tool execution plan
- Investigation task routing

Example queries:

- Why did incident INC-104 happen?
- Which services were affected in incident INC-101?
- Who owns payment-service?
- Show similar incidents.

Execution Type:

- Sequential

---

## 4.2 ContextBuilderAgent

### Role

Database and documentation outputs can be large.

The **ContextBuilderAgent compresses raw data** into a structured investigation context.

This prevents extremely large prompts being sent to reasoning agents.

## Input

Raw investigation data:

- incident details
- incident evidence
- service metadata
- documentation snippets
- historical incidents
- session history

## Output

Structured context:

```json
{
  "incident_summary": "...",
  "affected_services": [],
  "key_metrics": "...",
  "important_events": "...",
  "documentation_findings": "...",
  "historical_incidents": [],
  "service_owners": [],
  "escalation_contacts": []
}
```

Execution Type: Sequential

## 4.3 IncidentAnalysisAgent

Role

This agent performs core reasoning and root cause analysis.

It analyzes:

- incident evidence
- service dependencies
- documentation insights
- historical incident patterns

- Responsibilities:

- Identify root cause hypotheses
- Connect signals across systems
- Generate investigation insights
- Determine confidence level

Example output:

Root Cause Hypothesis:
Payment provider latency spike.

Supporting Evidence:
- payment_service_authz_latency_p95 increased
- gateway retry amplification
- historical incident INC-094 had similar pattern

Execution Type: Loop

The agent may request additional data if evidence is insufficient.

Loop termination conditions:

Follow the runtime policy and loop decision rules defined in section 3 (Loop Execution).

## 4.4 ResponseComposerAgent

Role

Generates the final structured response returned to the user.

Output format:

```json
{
  "summary": "...",
  "hypotheses": [
    {
      "cause": "...",
      "confidence": 0.82
    }
  ],
  "similar_incidents": [],
  "evidence": [],
  "owners": [],
  "escalation": [],
  "recommended_actions": [],
  "report": "Detailed incident report..."
}
```

Results are stored in:

messages.structured_json

Execution Type: Sequential

## 4.5 Agent Contracts (Strict)

All agents exchange a single typed context object.

`InvestigationContext` required fields:

```json
{
  "request_id": "string",
  "session_id": "uuid",
  "user_id": "integer",
  "query": "string",
  "incident_key": "string|null",
  "service_name": "string|null",
  "investigation_scope": "incident|service|ownership|comparison|report",
  "incident": "object|null",
  "services": "array",
  "evidence": "array",
  "docs": "array",
  "historical_incidents": "array",
  "session_history": "array",
  "context_content": {
    "incident_summary": "string",
    "affected_services": "array",
    "key_metrics": "array",
    "important_events": "array",
    "documentation_findings": "array",
    "historical_patterns": "array",
    "owners_and_escalation": "array",
    "open_questions": "array"
  },
  "hypotheses": "array",
  "confidence": "number",
  "status": "in_progress|complete|inconclusive|not_found|error"
}
```

`context_content` is mandatory before IncidentAnalysisAgent reasoning.  
Purpose: compact all fetched evidence into a high-signal context so the LLM reads less raw data and reduces hallucination risk.

Orchestrator contract:

- Input: `query`, `session_id`, optional `incident_key`
- Output:
  - `investigation_scope`: `incident|service|ownership|comparison|report`
  - `routing_target`: `context_builder|incident_analysis|response_composer`
  - `tool_plan[]`: array of
    - `tool`: string
    - `args`: object
    - `priority`: `high|medium|low`
    - `reason`: string

ContextBuilder contract:

- Input: raw tool outputs (`incident`, `services`, `evidence`, `docs`, `historical_incidents`, `session_history`)
- Output: normalized `InvestigationContext` with deduplicated entities, evidence references, and compact `context_content`

IncidentAnalysis contract:

- Input: `InvestigationContext`
- Output:
  - `hypotheses[]` where each item has `cause`, `confidence`, `supporting_evidence_refs[]`, `counter_evidence_refs[]`
  - `analysis_decision` as `continue|stop|inconclusive`
  - `missing_information[]`

ResponseComposer contract:

- Input: final `InvestigationContext` + `hypotheses[]`
- Output: schema-valid final JSON response (see section 4.4) with non-empty `summary`

# 5. Tools

Tools retrieve data while agents perform reasoning.

## 5.1 DatabaseTools

These tools query PostgreSQL.

- get_incident_by_key
- get_incident_services
- get_incident_evidence
- get_service_owner
- get_service_dependencies
- get_similar_incidents
- get_resolutions
- get_escalation_contacts
- load_session_messages
- save_assistant_message

Execution: Parallel

## 5.2 DocsTools

Documentation is stored in: resources/

Indexed by: resources/index.json

Tool: search_docs(query)

Returned structure:

```json
{
  "ok": true,
  "data": [
    {
      "doc_id": "payment_service_runbook",
      "category": "runbooks",
      "source_file": "resources/runbooks/payment-service-runbook.md",
      "service": "payment-service",
      "tags": ["payments", "latency"],
      "content_snippet": "...",
      "score": 0.88
    }
  ],
  "error": null,
  "source": "search_docs"
}
```

Execution: Parallel

## 5.3 Tool Contracts (Strict)

All tools must return JSON objects with:

- `ok` (boolean)
- `data` (object or array)
- `error` (null or object with `code` and `message`)
- `source` (tool name)

No-data behavior (required for all tools):

- If query succeeds but no records/documents match, return:
  - `ok = true`
  - `data = []` (or `{}` for object-returning tools)
  - `error = null`
- `ok = false` is only for execution/validation failures (timeouts, invalid arguments, DB errors, file read errors).

DatabaseTools contracts:

- `get_incident_by_key(incident_key: str)`  
  Returns `incidents` row fields: `id`, `incident_key`, `title`, `status`, `severity`, `started_at`, `resolved_at`, `summary`, `commander_user_id`.
- `get_incident_services(incident_key: str)`  
  Returns joined `incident_services + services`: `service_id`, `service_name`, `impact_type`, `tier`, `owner_user_id`, `runbook_path`.
- `get_incident_evidence(incident_key: str, limit: int=200)`  
  Returns `incident_evidence`: `id`, `service_id`, `event_type`, `event_time`, `metric_name`, `metric_value`, `unit`, `event_text`, `tags_json`, `metadata_json`.
- `get_service_owner(service_name: str)`  
  Returns joined `services + users`: `service_name`, `owner_user_id`, `owner_username`, `owner_email`, `owner_full_name`, `owner_role`.
- `get_service_dependencies(service_name: str)`  
  Returns `service_dependencies` graph edges: `service_name`, `depends_on_service_name`.
- `get_similar_incidents(incident_key: str, limit: int=5)`  
  Returns matched incidents with: `incident_key`, `title`, `severity`, `status`, `summary`, `similarity_reason`.
- `get_resolutions(incident_key: str)`  
  Returns `resolutions`: `resolution_summary`, `root_cause`, `actions_taken_json`, `resolved_at`, `resolved_by_user_id`.
- `get_escalation_contacts(service_name: str)`  
  Returns `escalation_contacts`: `name`, `contact_type`, `contact_value`, `priority_order`, `is_primary`.
- `load_session_messages(session_id: uuid, limit: int=30)`  
  Returns `messages`: `id`, `role`, `content_text`, `structured_json`, `created_at`.
- `save_assistant_message(session_id: uuid, content_text: str, structured_json: object)`  
  Persists a `messages` row and returns `message_id`.

DocsTools contract:

- `search_docs(query: str, top_k: int=5, category: str|null=null, service: str|null=null)`  
  Returns ranked items from `resources/index.json` documents with:
  - `doc_id`
  - `category`
  - `source_file`
  - `service` (nullable)
  - `tags`
  - `content_snippet`
  - `score`

Validation rules:

- All timestamps must be ISO-8601 UTC strings.
- `confidence` values must be within `[0.0, 1.0]`.
- If provided, `incident_key` must match `^INC-[0-9]+$`.
- Tool errors must never be embedded inside free text; use structured `error`.

# 6. Agentic RAG Workflow

Documentation retrieval follows Agentic RAG.

Agents decide when documentation is required.

Workflow:

```text
User Query
   ↓
OrchestratorAgent
   ↓
search_docs(query)
   ↓
resources/index.json
   ↓
Relevant Markdown Documents
   ↓
ContextBuilderAgent
```

# 7. Context Flow Between Agents

Agents exchange the canonical `InvestigationContext` defined in section 4.5.

Flow:

- Orchestrator initializes context with query/session metadata and tool plan.
- Retrieval tools populate raw fields (`incident`, `services`, `evidence`, `docs`, `historical_incidents`, `session_history`).
- ContextBuilder creates `context_content` as the compact reasoning payload.
- IncidentAnalysis reads `context_content` first, then references raw fields only when needed.
- ResponseComposer generates final output from hypotheses + context.

# 8. Error Handling and Edge Cases

The system must handle the following cases.

Missing Incident

If the incident key does not exist:

Return structured error response

Incomplete Evidence

IncidentAnalysisAgent triggers additional data retrieval.

No Relevant Documentation

Agent continues reasoning with database data only.

Large Context

ContextBuilderAgent compresses context before reasoning.

Conflicting Evidence

IncidentAnalysisAgent runs additional reasoning loops.

# 9. Implementation Order

Agents should be implemented in this order:

- DatabaseTools
- DocsTools (search_docs)
- Session tools
- OpsCopilotOrchestratorAgent
- ContextBuilderAgent
- IncidentAnalysisAgent
- ResponseComposerAgent

# 10. ADK Implementation Mapping

The implemented Google ADK path uses:

- Agent builders: `ops-agent/app/adk/agents.py`
- ADK execution runner: `ops-agent/app/adk/runner.py`
- Stage prompts: `ops-agent/app/prompts/orchestrator.md`, `context_builder.md`, `incident_analysis.md`, `response_composer.md`
- Workflow execution: `ops-agent/app/orchestration/pipeline.py`
- CLI full-run entrypoint: `ops-agent/run_agent.py`
