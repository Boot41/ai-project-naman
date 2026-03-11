# OpsCopilot Chatbot Manual Test Cases

Use these cases to manually validate frontend -> backend -> ops-agent behavior.

Format per case:
- Test ID
- User Input (or Conversation)
- Expected Bot Behavior
- Expected Output Signals

---

## 1) Incident Investigation (Happy Path)

### T01
- User Input: `Why did incident INC-104 happen?`
- Expected Bot Behavior: Explains likely cause with evidence-backed reasoning.
- Expected Output Signals: summary present, hypotheses array non-empty, status `complete|inconclusive`.

### T02
- User Input: `Summarize incident INC-101.`
- Expected Bot Behavior: Provides concise incident summary and key findings.
- Expected Output Signals: summary present, report present, status not `error`.

### T03
- User Input: `Which services were affected in incident INC-104?`
- Expected Bot Behavior: Lists impacted services and impact type if available.
- Expected Output Signals: affected services reflected in report/evidence, owners/escalation may be present.

### T04
- User Input: `Give root cause hypothesis for INC-101 with confidence.`
- Expected Bot Behavior: Returns one or more hypotheses with confidence.
- Expected Output Signals: hypotheses array with `cause` + `confidence` in [0,1].

### T05
- User Input: `Show timeline highlights for incident INC-104.`
- Expected Bot Behavior: Surfaces important events chronologically.
- Expected Output Signals: evidence/report includes timeline-like events.

### T06
- User Input: `What evidence supports the conclusion for INC-101?`
- Expected Bot Behavior: Links conclusions to evidence references.
- Expected Output Signals: evidence array populated, supporting refs in hypotheses.

### T07
- User Input: `Generate a full report for incident INC-104.`
- Expected Bot Behavior: Produces detailed structured output plus report narrative.
- Expected Output Signals: report non-empty, recommended_actions present.

---

## 2) Service Ownership

### T08
- User Input: `Who owns payment-service?`
- Expected Bot Behavior: Returns owner details if available.
- Expected Output Signals: owners array present, status `complete|inconclusive`.

### T09
- User Input: `Who is the escalation contact for payment-service?`
- Expected Bot Behavior: Returns escalation path/contacts.
- Expected Output Signals: escalation array present.

### T10
- User Input: `Give owner and escalation info for auth-service.`
- Expected Bot Behavior: Combines ownership and escalation in one response.
- Expected Output Signals: owners + escalation sections populated or marked insufficient.

### T11
- User Input: `Which team should handle search-service incidents?`
- Expected Bot Behavior: Maps service to ownership/escalation route.
- Expected Output Signals: owner contact info or explicit insufficient information.

---

## 3) Historical Incident Comparison

### T12
- User Input: `Have similar incidents happened before for INC-104?`
- Expected Bot Behavior: Compares current incident with historical incidents.
- Expected Output Signals: similar_incidents array present.

### T13
- User Input: `Show similar incidents for payment latency and their outcomes.`
- Expected Bot Behavior: Lists related incidents and resolution patterns.
- Expected Output Signals: similar_incidents + report includes comparison summary.

### T14
- User Input: `Compare INC-101 with past incidents by severity and services.`
- Expected Bot Behavior: Provides comparison dimensions and insights.
- Expected Output Signals: hypotheses/report mention similarities or differences.

### T15
- User Input: `What happened last time this failure pattern occurred?`
- Expected Bot Behavior: Uses historical incidents/resolutions if available.
- Expected Output Signals: similar_incidents or explicit insufficient info if none found.

---

## 4) Documentation Questions

### T16
- User Input: `How do we troubleshoot payment-service latency?`
- Expected Bot Behavior: Uses runbook/postmortem guidance.
- Expected Output Signals: evidence/report includes docs-derived guidance.

### T17
- User Input: `What does the incident response policy say for severe incidents?`
- Expected Bot Behavior: Summarizes policy-relevant guidance.
- Expected Output Signals: recommended actions reflect policy context.

### T18
- User Input: `Show architecture dependencies relevant to payment-service failures.`
- Expected Bot Behavior: Uses architecture docs + dependency data.
- Expected Output Signals: report references dependency/failure propagation context.

### T19
- User Input: `Which runbook steps apply to auth-service token validation issues?`
- Expected Bot Behavior: Returns actionable runbook guidance.
- Expected Output Signals: recommended_actions includes step-oriented items.

---

## 5) Follow-up Queries (Conversation Memory)

### T20
- Conversation:
  - User: `Why did incident INC-101 happen?`
  - User: `What was the root cause?`
- Expected Bot Behavior: Uses session memory; second answer should resolve reference to INC-101.
- Expected Output Signals: coherent follow-up without asking incident key again (unless missing context).

### T21
- Conversation:
  - User: `Summarize incident INC-104.`
  - User: `Who owned the affected services?`
- Expected Bot Behavior: Carries prior incident scope into follow-up.
- Expected Output Signals: owners data tied to earlier incident context.

### T22
- Conversation:
  - User: `Have similar incidents happened before?`
  - User: `What actions worked best?`
- Expected Bot Behavior: Follow-up builds on historical comparison context.
- Expected Output Signals: similar_incidents and recommended_actions aligned.

### T23
- Conversation:
  - User: `How do we troubleshoot payment-service latency?`
  - User: `Can you give only the top 3 steps?`
- Expected Bot Behavior: Refines prior answer based on user constraint.
- Expected Output Signals: concise recommended_actions in follow-up.

### T24
- Conversation:
  - User: `Why did incident INC-101 happen?`
  - User: `What evidence supports that?`
- Expected Bot Behavior: References evidence from same thread.
- Expected Output Signals: evidence section populated in follow-up.

---

## 6) Negative Cases

### T25
- User Input: `Why did incident INC-999 happen?`
- Expected Bot Behavior: Safe failure response, no fabrication.
- Expected Output Signals: status `not_found|inconclusive|error`, clear message like incident not found.

### T26
- User Input: `Give owner for unknown-service-xyz.`
- Expected Bot Behavior: Avoids guessing; returns insufficient information/safe error.
- Expected Output Signals: no fake owner data, clear next action.

### T27
- User Input: `Provide exact root cause without any data.`
- Expected Bot Behavior: Refuses speculation.
- Expected Output Signals: root cause undetermined / insufficient information, status likely `inconclusive`.

---

## 7) Edge Cases / Ambiguous Queries

### T28
- User Input: `Why is the system slow?`
- Expected Bot Behavior: Asks clarifying questions or requests incident/service scope.
- Expected Output Signals: clarification intent or insufficient-information guidance.

### T29
- User Input: `Something is broken in prod. Help.`
- Expected Bot Behavior: Requests concrete identifiers (incident key, service, timeframe).
- Expected Output Signals: safe triage-oriented next steps, no invented diagnosis.

### T30
- User Input: `Check this issue.`
- Expected Bot Behavior: Handles ambiguity safely by asking for specifics.
- Expected Output Signals: concise clarifying request; status may be `inconclusive`.

---

## Quick Manual Validation Checklist

For each response, verify:
- JSON is valid.
- Top-level has: `trace_id`, `status`, and `output` or `error`.
- If `output` exists, includes: `summary`, `hypotheses`, `similar_incidents`, `evidence`, `owners`, `escalation`, `recommended_actions`, `report`, `status`.
- No fabricated entities when data is missing.
- Ambiguous inputs trigger clarification or insufficient-information behavior.
