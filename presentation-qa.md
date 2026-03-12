# OpsCopilot Investigation Agent - Presentation Q&A

## 1. What is this project?
This project is an AI investigation assistant for operations incidents.  
It helps engineers ask questions in normal language and get evidence-backed answers using:
- PostgreSQL incident data
- Local docs (runbooks, postmortems, architecture docs, policies)
- Conversation memory from previous chat messages

## 2. What problem does it solve?
During incidents, engineers waste time jumping between dashboards, old tickets, docs, and chat history.  
This system collects and reasons over all those sources, then gives:
- summary of what is happening
- possible root cause with evidence
- similar past incidents
- ownership and escalation contacts
- report-style output

## 3. What is the high-level agent architecture?
It is a staged multi-agent pipeline:
1. `OpsCopilotOrchestratorAgent` - understands intent and plans tool calls
2. `RetrievalExecutor` - runs tools in parallel and merges results
3. `ContextBuilderAgent` - structures raw data into investigation context
4. `IncidentAnalysisAgent` - builds hypotheses, confidence, missing info
5. `ResponseComposerAgent` - prepares final structured response + report text

## 4. Why did we choose this architecture?
Because investigation is not one single step.
- Orchestrator separates intent/routing from data retrieval.
- Retrieval is parallel, so response is faster.
- Context builder standardizes mixed data (DB + docs + chat history).
- Analysis focuses on reasoning only.
- Composer focuses on final answer quality and response format.

This separation makes debugging and future upgrades easier.

## 5. Where does conversation memory happen?
Memory is session-based:
- Each session has many messages in DB.
- On each new query, the same `session_id` is sent to ops-agent.
- Tool `load_session_messages` fetches prior turns.
- Those messages are passed into context and analysis stages.

So follow-up user questions are answered with prior context.

## 6. Does the system ask clarifying questions by itself?
Current behavior: it uses existing session context, but does not run a full interactive clarification loop by default.  
If data is missing, it can return inconclusive output like “we don't have knowledge about this”.

## 7. What tools are available?
Main tool set:
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

## 8. Will every tool be called for every query?
No. Only relevant tools are called.

Tool selection is decided mainly by:
- detected intent (`incident`, `ownership`, `comparison`, `report`, `service`)
- what entities are found (`incident_key`, `service_name`)
- missing information after first analysis iteration

So tool usage is dynamic, not fixed.

## 9. How does the system decide what tool to call?
The Orchestrator creates a `tool_plan`.
- For ownership questions: owner + escalation tools are prioritized.
- For incident/root-cause questions: incident + resolution/evidence tools are added.
- For comparison: similar-incident tools are added.
- For all normal investigations: docs search + session history are usually included.

Then analysis can request more data, and a follow-up tool plan is generated.

## 10. Are tool calls sequential or parallel?
Planned retrieval tools are executed in parallel (fan-out), then merged into one context object.  
This improves speed and keeps architecture clean.

## 11. How do DB and docs both participate in reasoning?
The pipeline merges:
- structured DB records (incident, evidence, services, resolutions)
- unstructured doc snippets (`search_docs`)
- prior session messages

Then analysis uses all of them together to produce hypotheses and confidence.

## 12. What happens when PostgreSQL is unavailable?
Tool layer has a fallback to seed JSON data.  
So demo and development can still run with basic investigation responses.

## 13. What does the final output look like?
Structured JSON fields include:
- `summary`
- `hypotheses`
- `similar_incidents`
- `evidence`
- `owners`
- `escalation`
- `recommended_actions`
- `report`
- `status`

This is also stored in chat message history.

## 14. How is ownership and escalation identified?
Using service metadata and escalation contact tables/tools:
- map service -> owner
- map service -> ordered escalation contacts

This data is included in final response so responders know who to involve.

## 15. How is historical comparison done?
`get_similar_incidents` finds incidents with service overlap or similar severity.  
Then related details (like resolutions) are used to compare patterns and suggest likely next actions.

## 16. What are key strengths to highlight to a senior reviewer?
- Multi-source reasoning, not just keyword retrieval
- Evidence-aware structured response contract
- Clear stage boundaries (intent, retrieval, context, analysis, composition)
- Parallel retrieval for speed
- Session memory for follow-up continuity
- Graceful fallback paths when parts fail

## 17. What is one honest current limitation?
Clarification behavior can be improved.  
Today, when intent is vague, system may return inconclusive; a stronger next step is explicit clarification-question flow before full retrieval.

## 18. Which part of the architecture is sequential?
The overall stage flow is sequential:
1. Orchestrator
2. Retrieval
3. Context Builder
4. Incident Analysis
5. Response Composer

Each stage waits for the previous stage output.

## 19. Which part runs in parallel?
Tool retrieval runs in parallel (fan-out).  
If the tool plan has multiple tools, they are executed together and then merged.

Example:
- `get_incident_by_key`
- `get_incident_services`
- `search_docs`
- `load_session_messages`

These can run at the same time in one retrieval phase.

## 20. Which part is loop-based?
`IncidentAnalysisAgent` can run in a loop (up to configured iterations).  
If confidence is low or information is missing:
- analysis returns missing information
- follow-up tools are called
- analysis runs again

Loop stops when:
- confidence/decision is sufficient, or
- max iterations reached, or
- no useful follow-up plan exists

## 21. Is the whole system a LoopAgent/SequentialAgent in ADK terms?
Conceptually yes:
- It behaves like a sequential pipeline of stage agents.
- Analysis stage behaves like a loop step.
- Retrieval inside a step behaves like parallel fan-out.

So in simple words: **sequential pipeline + parallel retrieval + iterative analysis loop**.
