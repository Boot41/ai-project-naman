from __future__ import annotations

from google.adk.agents import Agent

from app.agents.runtime import (
    build_stage_agent,
    ensure_adk_key_configured,
    run_json_stage,
)
from app.contracts.response_composer import (
    ComposerInput,
    ComposerOutput,
    EscalationItem,
    EvidenceItem,
    OutputStatus,
    OwnerItem,
    SimilarIncidentItem,
)

RESPONSE_COMPOSER_PROMPT = """
<!--
agent_name: ResponseComposerAgent
version: 1.0.0
last_updated: 2026-03-11
owner: ops-agent
-->

You are ResponseComposerAgent.

Task:
- Produce final structured JSON response.
- Include summary, hypotheses, evidence, similar_incidents, owners, escalation, recommended_actions, report, status.

Rules:
- summary must be non-empty.
- If status=inconclusive include specific gap-focused recommended_actions.
- If documentation findings exist, recommended_actions must include concrete actions derived from those findings.
- Avoid generic actions such as "review docs"; provide operator-ready steps.
- Use only provided context and analysis outputs.
- Never invent incidents, services, owners, or metrics.
- If information is missing, explicitly state "insufficient information".
- Output strict JSON only matching ComposerOutput schema.
- Do not include markdown or extra text.
""".strip()


def build_response_composer_agent() -> Agent:
    return build_stage_agent(
        name="ResponseComposerAgent",
        instruction=RESPONSE_COMPOSER_PROMPT,
        tools=[],
    )


async def composer_with_adk_or_fallback(payload: ComposerInput) -> ComposerOutput:
    ensure_adk_key_configured()
    try:
        candidate = await run_json_stage(
            agent=build_response_composer_agent(),
            payload=payload,
            output_model=ComposerOutput,
            user_id=str(payload.session_id),
        )
        if payload.context_content.documentation_findings and (
            candidate.status.value == "inconclusive"
            or not candidate.recommended_actions
        ):
            return compose_response(payload)
        return candidate
    except Exception:
        return compose_response(payload)


def compose_response(payload: ComposerInput) -> ComposerOutput:
    summary = _build_summary(payload)
    similar_incidents = _extract_similar_incidents(payload)
    evidence = _extract_evidence(payload)
    owners = _extract_owners(payload)
    escalation = _extract_escalation(payload)
    recommended_actions = _recommended_actions(payload)
    report = _build_report(
        summary=summary,
        evidence=evidence,
        owners=owners,
        escalation=escalation,
        payload=payload,
    )

    output = ComposerOutput(
        summary=summary,
        hypotheses=payload.hypotheses,
        similar_incidents=similar_incidents,
        evidence=evidence,
        owners=owners,
        escalation=escalation,
        recommended_actions=recommended_actions,
        report=report,
        status=payload.status,
    )

    if output.status == OutputStatus.INCONCLUSIVE and not output.recommended_actions:
        raise ValueError("recommended_actions required when status is inconclusive")

    return output


def build_persistence_payload(output: ComposerOutput) -> dict[str, object]:
    return {
        "content_text": _to_human_readable(output),
        "structured_json": output.model_dump(),
    }


def build_response_composer_log(
    *,
    output: ComposerOutput,
    latency_ms: int,
    status: str,
) -> dict[str, str | int]:
    return {
        "agent": "ResponseComposerAgent",
        "output_status": output.status.value,
        "hypothesis_count": len(output.hypotheses),
        "evidence_count": len(output.evidence),
        "latency_ms": latency_ms,
        "status": status,
    }


def _build_summary(payload: ComposerInput) -> str:
    if payload.status == OutputStatus.NOT_FOUND:
        return "Requested incident/service context was not found."
    if payload.status == OutputStatus.ERROR:
        return "Investigation could not be completed due to an internal error."

    if payload.hypotheses:
        top = max(payload.hypotheses, key=lambda h: h.confidence)
        return (
            f"Primary hypothesis: {top.cause} "
            f"(confidence {top.confidence:.2f}) based on available evidence."
        )

    return (
        payload.context_content.incident_summary or "Investigation summary generated."
    )


def _extract_similar_incidents(payload: ComposerInput) -> list[SimilarIncidentItem]:
    out: list[SimilarIncidentItem] = []
    for pattern in payload.context_content.historical_patterns:
        out.append(
            SimilarIncidentItem(
                incident_key=pattern.incident_key,
                similarity_reason=pattern.pattern,
            )
        )
    return out


def _extract_evidence(payload: ComposerInput) -> list[EvidenceItem]:
    out: list[EvidenceItem] = []

    for event in payload.context_content.important_events:
        out.append(
            EvidenceItem(ref=event.event_id, source="db", snippet=event.event_text)
        )

    for finding in payload.context_content.documentation_findings:
        out.append(
            EvidenceItem(
                ref=finding.doc_id,
                source="docs",
                snippet=finding.finding,
            )
        )

    return out


def _extract_owners(payload: ComposerInput) -> list[OwnerItem]:
    out: list[OwnerItem] = []
    for item in payload.context_content.owners_and_escalation:
        out.append(OwnerItem(service_name=item.service_name, owner=item.owner))
    return out


def _extract_escalation(payload: ComposerInput) -> list[EscalationItem]:
    out: list[EscalationItem] = []
    for item in payload.context_content.owners_and_escalation:
        out.append(
            EscalationItem(
                service_name=item.service_name, contacts=item.escalation_contacts
            )
        )
    return out


def _recommended_actions(payload: ComposerInput) -> list[str]:
    actions: list[str] = []

    for finding in payload.context_content.documentation_findings[:4]:
        snippet = finding.finding.strip()
        if not snippet:
            continue
        actions.append(f"Runbook action ({finding.doc_id}): {snippet}")

    if payload.status == OutputStatus.INCONCLUSIVE:
        for gap in payload.context_content.open_questions:
            actions.append(f"Resolve gap: {gap}")

    if payload.hypotheses:
        actions.append("Validate primary hypothesis with latest telemetry and logs.")
        actions.append(
            "Apply or verify runbook mitigation steps for impacted services."
        )

    if not actions:
        actions.append(
            "Continue monitoring and collect additional evidence if conditions change."
        )

    # preserve order and remove duplicates
    seen: set[str] = set()
    deduped: list[str] = []
    for action in actions:
        if action in seen:
            continue
        seen.add(action)
        deduped.append(action)
    return deduped


def _build_report(
    *,
    summary: str,
    evidence: list[EvidenceItem],
    owners: list[OwnerItem],
    escalation: list[EscalationItem],
    payload: ComposerInput,
) -> str:
    timeline = "\n".join(
        f"- {evt.event_time}: {evt.event_text}"
        for evt in payload.context_content.important_events
    )
    if not timeline:
        timeline = "- No timeline events available"

    affected_services = (
        ", ".join(s.service_name for s in payload.context_content.affected_services)
        or "N/A"
    )
    likely_root_cause = (
        payload.hypotheses[0].cause if payload.hypotheses else "Not determined"
    )

    evidence_trail = "\n".join(
        f"- {item.ref}: {item.snippet}" for item in evidence[:10]
    )
    if not evidence_trail:
        evidence_trail = "- No evidence trail available"

    mitigations = "\n".join(f"- {action}" for action in _recommended_actions(payload))

    owner_lines = (
        "\n".join(f"- {o.service_name}: {o.owner or 'unknown'}" for o in owners)
        or "- None"
    )
    escalation_lines = (
        "\n".join(
            f"- {e.service_name}: {', '.join(e.contacts) if e.contacts else 'no contacts'}"
            for e in escalation
        )
        or "- None"
    )

    return (
        f"Summary\n{summary}\n\n"
        f"Timeline Highlights\n{timeline}\n\n"
        f"Affected Services\n- {affected_services}\n\n"
        f"Likely Root Cause\n- {likely_root_cause}\n\n"
        f"Evidence Trail\n{evidence_trail}\n\n"
        f"Owners\n{owner_lines}\n\n"
        f"Escalation\n{escalation_lines}\n\n"
        f"Mitigations and Next Steps\n{mitigations}"
    )


def _to_human_readable(output: ComposerOutput) -> str:
    top = output.hypotheses[0].cause if output.hypotheses else "N/A"
    return (
        f"Summary: {output.summary}\n"
        f"Status: {output.status.value}\n"
        f"Top Hypothesis: {top}\n"
        f"Recommended Actions: {len(output.recommended_actions)}"
    )
