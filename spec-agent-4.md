# Spec Agent 4: ResponseComposerAgent

## 1. Purpose

ResponseComposerAgent generates final user-facing structured output from analysis results.

## 2. Responsibilities

- Produce concise summary.
- Present hypotheses with confidence.
- Present evidence and similar incidents.
- Include owners/escalation and recommended actions.
- Optionally produce full incident report body.

## 3. Input Contract

```json
{
  "request_id": "string",
  "session_id": "uuid",
  "query": "string",
  "investigation_scope": "incident|service|ownership|comparison|report",
  "context_content": {},
  "hypotheses": [],
  "confidence": 0.0,
  "status": "complete|inconclusive|not_found|error"
}
```

## 4. Final Output Contract

```json
{
  "summary": "string",
  "hypotheses": [
    {
      "cause": "string",
      "confidence": 0.0,
      "supporting_evidence_refs": ["string"],
      "counter_evidence_refs": ["string"]
    }
  ],
  "similar_incidents": [
    {
      "incident_key": "string",
      "similarity_reason": "string"
    }
  ],
  "evidence": [
    {
      "ref": "string",
      "source": "db|docs|session",
      "snippet": "string"
    }
  ],
  "owners": [
    {
      "service_name": "string",
      "owner": "string|null"
    }
  ],
  "escalation": [
    {
      "service_name": "string",
      "contacts": []
    }
  ],
  "recommended_actions": ["string"],
  "report": "string",
  "status": "complete|inconclusive|not_found|error"
}
```

Constraints:

- `summary` required and non-empty.
- `confidence` must be `[0.0, 1.0]`.
- If `status=inconclusive`, include specific gaps in `recommended_actions`.

## 5. Report Generation Rules

For `report`:

- include timeline highlights
- include affected services
- include likely root cause
- include evidence trail
- include mitigations and next steps

## 6. Persistence Rules

Save composed JSON into `messages.structured_json` and human-readable text in `messages.content_text`.

## 7. ADK Implementation Notes

- Final node in pipeline.
- Strict JSON serializer with schema validation before persistence.
- If validation fails, retry one reformat pass.

Implementation mapping:

- Agent builder + prompt + fallback wrapper: `ops-agent/app/agents/response_composer_agent.py`
  - `build_response_composer_agent`
  - `composer_with_adk_or_fallback`
- Shared ADK stage runner: `ops-agent/app/agents/runtime.py` (`run_json_stage`)

## 8. Logging Events

```json
{
  "trace_id": "string",
  "agent": "ResponseComposerAgent",
  "output_status": "complete|inconclusive|not_found|error",
  "hypothesis_count": 0,
  "evidence_count": 0,
  "latency_ms": 0,
  "status": "success|error"
}
```

## 9. Acceptance Criteria

- Output JSON validates against contract.
- Report is generated when requested.
- Structured output is persisted.
- No hallucinated claims without evidence references.
