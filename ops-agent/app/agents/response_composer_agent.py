from __future__ import annotations

import re

from google.adk.agents import Agent

from app.agents.runtime import build_stage_agent, run_json_stage_with_timeout
from app.contracts.response_composer import (
    ComposerInput,
    ComposerOutput,
    EscalationItem,
    EvidenceItem,
    OutputStatus,
    OwnerItem,
    SimilarIncidentItem,
)
_RAW_OWNER_ID_PATTERN = re.compile(r"\buser\s*id\s*\d+\b(?:\s*\([^)]*\))?", re.IGNORECASE)

AGENT_NAME = "ResponseComposerAgent"
RESPONSE_COMPOSER_PROMPT = """
You are ResponseComposerAgent.
Return valid ComposerOutput JSON only.
Input-handoff rule:
- Use latest IncidentAnalysisOutput and ContextBuilderOutput from prior stages.
- Preserve evidence refs from analysis/context; do not create fake refs.
Never wrap output in markdown or code fences.
Never return placeholder/meta responses such as:
- "No more outputs are needed"
- "already processed"
- "cannot provide further output"
Every user turn must produce a complete final answer in ComposerOutput schema.
Quality bar:
- Make summary concise (2-4 sentences) and directly answer user query.
- In `report`, use this structure:
  1) Evidence-backed findings
  2) Inferred (lower-confidence) considerations
  3) Gaps / unknowns
- Never mix inferred claims into evidence-backed section.
- `recommended_actions` must be exactly top 3 immediate actions, ordered by impact and urgency.
- Each action must be concrete and operational (owner/team + what to check/do).
- If evidence is insufficient, explicitly state "insufficient information" and keep actions as data-gathering steps.
- Avoid repetition and generic advice.
For documentation/policy/architecture questions:
- answer directly from documentation findings
- include concrete policy/dependency points in summary, not generic "guidance retrieved"
- keep status `complete` when docs evidence exists
Status rule:
- use `complete` only when summary/hypotheses/evidence are consistent.
- use `inconclusive` when key evidence is missing or contradictory.
For payment-service latency queries, prioritize actions in this order unless evidence strongly contradicts it:
1) external payment processor health/latency check,
2) retry amplification control in upstream services (`order-service`, `api-gateway`),
3) payment-event queue backlog mitigation with concrete rollback/flag/traffic controls.
""".strip()

response_composer_agent = build_stage_agent(
    name=AGENT_NAME,
    instruction=RESPONSE_COMPOSER_PROMPT,
    tools=[],
)


def build_response_composer_agent() -> Agent:
    return response_composer_agent


async def composer_with_adk_or_fallback(payload: ComposerInput) -> ComposerOutput:
    try:
        output = await run_json_stage_with_timeout(
            agent=response_composer_agent,
            payload=payload,
            output_model=ComposerOutput,
            user_id=str(payload.session_id),
            timeout_seconds=45,
        )
        return _normalize_output_sources(output, payload)
    except Exception:
        pass

    summary = (
        "Investigation is inconclusive due to insufficient information."
        if payload.status == OutputStatus.INCONCLUSIVE
        else (payload.context_content.incident_summary or "Investigation completed.")
    )
    query_lower = payload.query.lower()
    is_docs_guidance = any(
        token in query_lower
        for token in ("policy", "runbook", "postmortem", "architecture", "dependency")
    )
    if is_docs_guidance and payload.context_content.documentation_findings:
        first_doc = payload.context_content.documentation_findings[0]
        summary = first_doc.finding[:260] or summary
    is_payment_latency = (
        "payment-service" in query_lower and "latency" in query_lower
    ) or ("payment" in query_lower and "latency" in query_lower)
    if is_docs_guidance:
        if "policy" in query_lower:
            fallback_actions = [
                "Apply severe-incident criteria from policy to classify current impact and severity.",
                "Assign required severe-incident roles and responsibilities per policy.",
                "Execute policy-defined escalation and communications timeline.",
            ]
        elif "architecture" in query_lower or "dependency" in query_lower:
            fallback_actions = [
                "Validate payment-service critical dependencies in order: provider, order-service, api-gateway, auth-service.",
                "Check retry/circuit-breaker behavior on upstream callers to limit blast radius during payment degradation.",
                "Use dependency map to prioritize mitigations on Tier 1 path before lower-priority services.",
            ]
        else:
            fallback_actions = [
                "Use cited documentation points as the immediate execution checklist.",
                "Validate current telemetry against documentation assumptions before applying mitigations.",
                "Record actions with evidence refs in the incident timeline.",
            ]
    elif is_payment_latency:
        fallback_actions = [
            "Payments On-call: validate external payment processor health (status page, auth roundtrip latency, error codes) and isolate provider-specific degradation.",
            "Platform SRE: reduce retry amplification from order-service and api-gateway (retry budget, backoff, temporary circuit-break/traffic shaping).",
            "Payments Team: mitigate queue backlog in payment-service (pause non-critical async work, scale workers, rollback recent risky changes) and verify p95/p99 recovery.",
        ]
    else:
        fallback_actions = (
            [f"Resolve gap: {q}" for q in payload.context_content.open_questions[:3]]
            if payload.context_content.open_questions
            else [
                "Validate current customer impact and error/latency trends on the affected service.",
                "Check upstream/downstream dependencies and external provider health for correlated degradation.",
                "Apply the safest reversible mitigation (rollback, feature-flag disable, or traffic shaping) and monitor recovery.",
            ]
        )
    report = (
        "Evidence-backed findings:\n"
        + (
            "\n".join(
                f"- {item.finding}"
                for item in payload.context_content.documentation_findings[:3]
            )
            or "- insufficient information"
        )
        + "\nInferred (lower-confidence) considerations:\n"
        + (
            "\n".join(f"- {h.reasoning_summary}" for h in payload.hypotheses[:2])
            or "- insufficient information"
        )
        + "\nGaps / unknowns:\n"
        + (
            "\n".join(f"- {q}" for q in payload.context_content.open_questions[:3])
            or "- no major unresolved gaps identified"
        )
    )

    return ComposerOutput(
        summary=summary,
        hypotheses=payload.hypotheses,
        similar_incidents=[
            SimilarIncidentItem(
                incident_key=i.incident_key, similarity_reason=i.pattern
            )
            for i in payload.context_content.historical_patterns
        ],
        evidence=[
            EvidenceItem(ref=i.event_id, source="db", snippet=i.event_text)
            for i in payload.context_content.important_events
        ]
        + [
            EvidenceItem(ref=i.doc_id, source="docs", snippet=i.finding)
            for i in payload.context_content.documentation_findings
        ],
        owners=[
            OwnerItem(service_name=i.service_name, owner=i.owner)
            for i in payload.context_content.owners_and_escalation
        ],
        escalation=[
            EscalationItem(service_name=i.service_name, contacts=i.escalation_contacts)
            for i in payload.context_content.owners_and_escalation
        ],
        recommended_actions=fallback_actions,
        report=report,
        status=OutputStatus.COMPLETE if is_docs_guidance and payload.context_content.documentation_findings else payload.status,
    )


def _normalize_output_sources(output: ComposerOutput, payload: ComposerInput) -> ComposerOutput:
    db_refs = {item.event_id for item in payload.context_content.important_events}
    doc_refs = {item.doc_id for item in payload.context_content.documentation_findings}

    normalized: list[EvidenceItem] = []
    for item in output.evidence:
        source = item.source
        if item.ref in db_refs:
            source = "db"
        elif item.ref in doc_refs:
            source = "docs"
        normalized.append(item.model_copy(update={"source": source}))

    cleaned_owners: list[OwnerItem] = []
    for owner in output.owners:
        owner_value = _clean_owner_text(owner.owner)
        cleaned_owners.append(owner.model_copy(update={"owner": owner_value}))

    cleaned_summary = _sanitize_text(output.summary)
    cleaned_actions = [_sanitize_text(action) for action in output.recommended_actions]
    cleaned_report = _sanitize_text(output.report)

    cleaned_hypotheses = [
        hypothesis.model_copy(
            update={
                "cause": _sanitize_text(hypothesis.cause),
                "reasoning_summary": _sanitize_text(hypothesis.reasoning_summary),
            }
        )
        for hypothesis in output.hypotheses
    ]
    cleaned_evidence = [
        item.model_copy(update={"snippet": _sanitize_text(item.snippet)}) for item in normalized
    ]

    return output.model_copy(
        update={
            "summary": cleaned_summary,
            "evidence": cleaned_evidence,
            "owners": cleaned_owners,
            "recommended_actions": cleaned_actions,
            "report": cleaned_report,
            "hypotheses": cleaned_hypotheses,
        }
    )


def _sanitize_text(value: str) -> str:
    return _RAW_OWNER_ID_PATTERN.sub("service owner", value).strip()


def _clean_owner_text(owner: str | None) -> str | None:
    if owner is None:
        return None
    cleaned = _RAW_OWNER_ID_PATTERN.sub("", owner).strip(" -:()")
    return cleaned or None
