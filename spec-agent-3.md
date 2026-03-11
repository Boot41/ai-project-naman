# Spec Agent 3: IncidentAnalysisAgent

## 1. Purpose

IncidentAnalysisAgent performs root-cause reasoning over `context_content` and linked evidence.
It may execute in a controlled loop to request additional data.

## 2. Responsibilities

- Generate evidence-backed hypotheses.
- Score confidence per hypothesis.
- Identify missing evidence.
- Decide continue vs stop.

## 3. Input Contract

```json
{
  "request_id": "string",
  "session_id": "uuid",
  "query": "string",
  "investigation_scope": "incident|service|ownership|comparison|report",
  "context_content": {},
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
  "hypotheses": [
    {
      "cause": "string",
      "confidence": 0.0,
      "supporting_evidence_refs": ["string"],
      "counter_evidence_refs": ["string"],
      "reasoning_summary": "string"
    }
  ],
  "analysis_decision": "continue|stop|inconclusive",
  "missing_information": ["string"],
  "confidence": 0.0,
  "status": "in_progress|complete|inconclusive"
}
```

## 5. Loop Runtime Policy

- `max_iterations = 3`
- `target_confidence = 0.75`
- `per_tool_timeout_seconds = 8`
- `per_iteration_budget_seconds = 20`
- `analysis_total_budget_seconds = 60`
- `max_additional_tool_calls_per_iteration = 4`

Stop rules:

- stop when best hypothesis `>= target_confidence` and at least 2 independent supporting evidence refs.
- continue when confidence below threshold and useful unresolved gaps exist.
- mark `inconclusive` when time/iteration budget exhausted.

## 6. Additional Tool Call Rules

Agent may request extra retrieval only for explicit gaps:

- missing service dependency evidence
- missing owner/escalation evidence
- missing historical pattern support
- conflicting event chronology

No duplicate call with identical args within same iteration.

## 7. Reasoning Constraints

- No speculation without evidence refs.
- Every causal statement must map to at least one evidence ref.
- Use docs as supportive context, not as sole proof for incident-specific facts.
- If contradictory evidence exists, include it in `counter_evidence_refs`.

## 8. Confidence Scoring Guidance

- 0.80-1.00: multiple independent strong evidence signals
- 0.60-0.79: partial but coherent evidence chain
- 0.40-0.59: weak or incomplete support
- <0.40: mostly speculative or unresolved

## 9. ADK Implementation Notes

- Use loop-capable node with explicit state transitions.
- Persist iteration summaries in context for debugging.
- Keep temperature low to maintain determinism.

Implementation mapping:

- Agent builder + prompt + loop wrapper: `ops-agent/app/agents/incident_analysis_agent.py`
  - `build_incident_analysis_agent`
  - `analysis_with_adk_or_fallback`
- Shared ADK stage runner: `ops-agent/app/agents/runtime.py` (`run_json_stage`)

## 10. Logging Events

Per iteration, emit:

```json
{
  "trace_id": "string",
  "agent": "IncidentAnalysisAgent",
  "iteration": 1,
  "requested_additional_tools": [],
  "received_evidence_count": 0,
  "best_confidence": 0.0,
  "decision": "continue|stop|inconclusive",
  "latency_ms": 0,
  "status": "success|error"
}
```

## 11. Acceptance Criteria

- Every hypothesis has evidence refs.
- Loop limits are always enforced.
- Inconclusive outcome is explicit when evidence is insufficient.
- Output JSON always valid.
