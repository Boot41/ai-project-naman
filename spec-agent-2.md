# Spec Agent 2: ContextBuilderAgent

## 1. Purpose

ContextBuilderAgent transforms raw retrieval output into compact `context_content` so downstream reasoning is grounded and concise.

This step is mandatory before IncidentAnalysisAgent.

## 2. Responsibilities

- Normalize and deduplicate raw records.
- Link evidence to service and incident entities.
- Build compact, high-signal `context_content`.
- Preserve references to raw evidence ids for traceability.

## 3. Input Contract

```json
{
  "request_id": "string",
  "session_id": "uuid",
  "user_id": 123,
  "query": "string",
  "incident_key": "string|null",
  "service_name": "string|null",
  "investigation_scope": "incident|service|ownership|comparison|report",
  "incident": {},
  "services": [],
  "evidence": [],
  "docs": [],
  "historical_incidents": [],
  "session_history": []
}
```

## 4. Output Contract

```json
{
  "request_id": "string",
  "session_id": "uuid",
  "user_id": 123,
  "query": "string",
  "incident_key": "string|null",
  "service_name": "string|null",
  "investigation_scope": "incident|service|ownership|comparison|report",
  "incident": {},
  "services": [],
  "evidence": [],
  "docs": [],
  "historical_incidents": [],
  "session_history": [],
  "context_content": {
    "incident_summary": "string",
    "affected_services": [
      {
        "service_name": "string",
        "tier": "string|null",
        "impact_type": "string|null"
      }
    ],
    "key_metrics": [
      {
        "metric_name": "string",
        "value": "number|null",
        "unit": "string|null",
        "event_time": "ISO-8601"
      }
    ],
    "important_events": [
      {
        "event_id": "string",
        "event_type": "string",
        "event_time": "ISO-8601",
        "event_text": "string"
      }
    ],
    "documentation_findings": [
      {
        "doc_id": "string",
        "category": "string",
        "source_file": "string",
        "finding": "string"
      }
    ],
    "historical_patterns": [
      {
        "incident_key": "string",
        "pattern": "string",
        "relevance": "high|medium|low"
      }
    ],
    "owners_and_escalation": [
      {
        "service_name": "string",
        "owner": "string|null",
        "escalation_contacts": []
      }
    ],
    "open_questions": [
      "string"
    ]
  },
  "status": "in_progress"
}
```

## 5. Compression Rules

- Keep only information relevant to current scope.
- Prefer structured metrics/events over long free text.
- Limit `important_events` to top 15 by impact and recency.
- Limit `documentation_findings` to top 8 highest-scored snippets.
- Include only evidence directly connected to query entities.

## 6. Deduplication Rules

- Dedupe services by `service_name`.
- Dedupe evidence by `incident_evidence.id`.
- Dedupe docs by `doc_id + source_file`.
- Dedupe historical incidents by `incident_key`.

## 7. Open Question Generation Rules

Create `open_questions` when:

- no incident row found
- weak/contradictory evidence
- missing owner/escalation details
- docs have no relevant findings

## 8. ADK Implementation Notes

- Use deterministic formatting instructions.
- Keep prompt context budget small by passing `context_content` to analysis agent as primary payload.
- Include raw arrays in context for optional drill-down only.

Implementation mapping:

- Agent builder + prompt + fallback wrapper: `ops-agent/app/agents/context_builder_agent.py`
  - `build_context_builder_agent`
  - `context_builder_with_adk_or_fallback`
- Shared ADK stage runner: `ops-agent/app/agents/runtime.py` (`run_json_stage`)

## 9. Failure Handling

- If no data returned from all retrieval tools, set:
  - `context_content.incident_summary = "No relevant data found"`
  - `open_questions` with targeted next-step questions.
- Return `status=not_found` when core entity is absent.

## 10. Logging Events

```json
{
  "trace_id": "string",
  "agent": "ContextBuilderAgent",
  "raw_evidence_count": 0,
  "compressed_event_count": 0,
  "doc_count": 0,
  "open_question_count": 0,
  "latency_ms": 0,
  "status": "success|error"
}
```

## 11. Acceptance Criteria

- Produces `context_content` for every successful retrieval path.
- Output remains bounded and compact.
- All compressed entries preserve back-reference ids/keys.
- Output JSON validates against contract.
