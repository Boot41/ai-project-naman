# OpsCopilot Agentic Workflow System

## 1. System Overview

OpsCopilot is an AI assistant for incident investigation.  
It helps operations engineers answer questions such as:

- What happened in an incident?
- Who owns a failing service?
- What mitigation steps should be taken now?

It combines two knowledge sources:

- **Operational data** (incident, services, evidence, ownership, escalation, history)
- **Documentation corpus** (runbooks, postmortems, policies, architecture docs)

The goal is to produce **evidence-backed, structured responses** instead of generic chatbot text.

## 2. End-to-End Flow

```text
Frontend (chat UI)
  -> Backend API (server)
  -> Ops-Agent API (/v1/investigate)
  -> Multi-agent investigation flow
  -> Structured response
  -> Backend returns to frontend
```

High-level request path:

1. User sends a chat question in frontend.
2. Backend authenticates user and calls Ops-Agent.
3. Ops-Agent runs the multi-agent workflow.
4. Ops-Agent returns structured JSON.
5. Backend maps/persists response and returns it to frontend.

ADK Web test path (graph entry in `ops-agent`):

```text
ADK Web (adk_app)
  -> root_agent export (adk_app/agent.py)
  -> OpsCopilot multi-agent graph
  -> Structured response
```

## 3. Agent Architecture

### Root Graph Agent (`OpsCopilotInvestigationFlow`)

- ADK graph root for investigation execution.
- Runs stage agents in sequence for traceability.
- Used for ADK Web visualization and API runtime entry.

### OpsCopilotOrchestratorAgent

- Entry agent for investigation.
- Classifies request intent/scope.
- Builds tool retrieval plan.
- Routes flow to context builder.
- Applies docs category routing for policy/runbook/postmortem/architecture queries.

### ContextBuilderAgent

- Combines retrieved DB and docs signals.
- Compresses noisy raw data into investigation context.
- Produces normalized context for analysis.

### IncidentAnalysisAgent

- Performs root-cause reasoning on context.
- Produces hypotheses with confidence and evidence refs.
- Can ask for more retrieval if evidence is missing.

### ResponseComposerAgent

- Generates final user-facing structured JSON.
- Includes summary, hypotheses, evidence, owners, escalation, actions, report, status.

## 4. Agentic Workflow

```text
User Query
  -> Orchestrator
  -> Context Builder
  -> Incident Analysis (loop if needed)
  -> Response Composer
  -> Final JSON
```

Key execution behavior:

- **Sequential stages** for reasoning quality and traceability.
- **Analysis loop** for missing-information recovery before final response.
- Retrieval tools are still available at agent/tool layer for evidence grounding.
- API and ADK Web both execute the same `root_agent` path.

## 5. Tools Layer

Ops-Agent uses a constrained tool set.

### DatabaseTools

- `get_incident_by_key`
- `get_incident_services`
- `get_incident_evidence`
- `get_service_owner`
- `get_service_dependencies`
- `get_similar_incidents`
- `get_resolutions`
- `get_escalation_contacts`
- `load_session_messages`
- `get_investigation_bundle`

### DocsTools

- `search_docs(query, top_k, category, service)`

Notes:

- Tool responses use a structured envelope (`ok/data/error/source`).
- Message persistence is owned by backend server side, not ops-agent orchestration.
- DB tool path is DB-first with seed fallback (`server/seed_data`) when DB is unavailable.
- Docs retrieval uses `ops-agent/resources/index.json` + markdown corpus under `ops-agent/resources/**`.

## 6. Agentic RAG

OpsCopilot applies Agentic RAG for documentation grounding:

1. `search_docs` reads **`ops-agent/resources/index.json`** (resource index).
2. It ranks matching markdown files in `ops-agent/resources/**`.
3. It returns high-signal snippets with metadata (`doc_id`, `category`, `source_file`, `score`).
4. Context/analysis agents use this as evidence, alongside DB signals.

This gives retrieval-backed answers rather than pure model memory.

## 7. Structured Response Format

Top-level ops-agent response:

```json
{
  "trace_id": "string",
  "status": "complete|inconclusive|not_found|error",
  "output": {
    "summary": "string",
    "hypotheses": [],
    "similar_incidents": [],
    "evidence": [],
    "owners": [],
    "escalation": [],
    "recommended_actions": [],
    "report": "string",
    "status": "complete|inconclusive|not_found|error"
  },
  "error": null,
  "logs": [],
  "persistence": null
}
```

If investigation fails, `output` is `null` and `error` is populated.

## 8. Error Handling & Edge Cases

Handled cases include:

- **Missing incident key / incident not found** -> structured `not_found`/inconclusive path.
- **Unknown service** -> no-data tool responses; agent asks for more details.
- **Insufficient evidence** -> explicit inconclusive response with next actions.
- **Tool execution failures/timeouts** -> structured error payload, never raw stack traces to user.
- **Docs-only guidance queries** -> docs-grounded `complete` response when evidence exists.

Design principle:

- Prefer explicit `"insufficient information"` over hallucinated conclusions.

## 9. Project Folder Structure

```text
client/
  src/lib/api.ts                 # frontend API client

server/
  app/api/                       # backend endpoints
  app/services/agent_client.py   # backend -> ops-agent bridge
  app/services/chat.py           # chat orchestration

ops-agent/
  app/main.py                    # /v1/investigate API
  app/service.py                 # service entry
  app/investigation_entry.py     # shared API entrypoint
  app/agents/
    orchestrator_agent.py
    context_builder_agent.py
    incident_analysis_agent.py
    response_composer_agent.py
    runtime.py
  app/services/
    enrichment.py
    output_normalizer.py
  adk_app/
    agent.py                     # ADK Web root agent export
  app/tools/
    agent_tools.py
    docs_search.py
    contracts.py
  app/contracts/                 # Pydantic stage contracts
  resources/
    index.json
    runbooks/*.md
    postmortems/*.md
    policies/*.md
    architecture/*.md
```

This structure keeps concerns separated:

- UI in `client`
- auth/business/persistence in `server`
- agentic investigation intelligence in `ops-agent`
