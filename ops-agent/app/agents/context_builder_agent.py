from __future__ import annotations

from datetime import datetime

from google.adk.agents import Agent

from app.agents.runtime import (
    build_stage_agent,
    ensure_adk_key_configured,
    run_json_stage,
)
from app.contracts.context_builder import (
    AffectedService,
    ContextBuilderInput,
    ContextBuilderOutput,
    ContextContent,
    DocumentationFinding,
    HistoricalPattern,
    ImportantEvent,
    KeyMetric,
    OwnerEscalation,
    PatternRelevance,
)
from app.contracts.orchestrator import InvestigationScope

CONTEXT_BUILDER_PROMPT = """
<!--
agent_name: ContextBuilderAgent
version: 1.0.0
last_updated: 2026-03-11
owner: ops-agent
-->

You are ContextBuilderAgent.

Task:
- Transform raw retrieval outputs into compact context_content.
- Deduplicate services/evidence/docs/historical incidents.
- Keep important_events <= 15 and documentation_findings <= 8.
- Include open_questions for missing/weak evidence.

Rules:
- Use only provided context; do not infer missing facts.
- Never invent incidents, services, owners, or metrics.
- If information is missing, explicitly state "insufficient information".
- Output strict JSON only matching ContextBuilderOutput schema.
- Preserve evidence references when possible.
- Keep content concise and high-signal.
""".strip()


def build_context_builder_agent() -> Agent:
    return build_stage_agent(
        name="ContextBuilderAgent",
        instruction=CONTEXT_BUILDER_PROMPT,
        tools=[],
    )


async def context_builder_with_adk_or_fallback(
    payload: ContextBuilderInput,
) -> ContextBuilderOutput:
    ensure_adk_key_configured()
    try:
        return await run_json_stage(
            agent=build_context_builder_agent(),
            payload=payload,
            output_model=ContextBuilderOutput,
            user_id=str(payload.user_id),
        )
    except Exception:
        return build_investigation_context(payload)


def build_investigation_context(payload: ContextBuilderInput) -> ContextBuilderOutput:
    services = _dedupe_services(payload.services)
    evidence = _dedupe_evidence(payload.evidence)
    docs = _dedupe_docs(payload.docs)
    historical_incidents = _dedupe_historical(payload.historical_incidents)

    affected_services = _build_affected_services(services)
    key_metrics = _build_key_metrics(evidence)
    important_events = _build_important_events(evidence)
    documentation_findings = _build_documentation_findings(docs)
    historical_patterns = _build_historical_patterns(historical_incidents)
    owners_and_escalation = _build_owners_and_escalation(services)

    incident_summary = _build_incident_summary(payload, evidence)
    open_questions = _build_open_questions(
        payload=payload,
        incident_found=payload.incident is not None,
        evidence=evidence,
        documentation_findings=documentation_findings,
        owners_and_escalation=owners_and_escalation,
    )

    if _is_fully_empty(payload, services, evidence, docs, historical_incidents):
        incident_summary = "No relevant data found"

    status = "in_progress"
    if (
        payload.investigation_scope
        in {
            InvestigationScope.INCIDENT,
            InvestigationScope.REPORT,
        }
        and payload.incident_key
        and payload.incident is None
    ):
        status = "not_found"

    context_content = ContextContent(
        incident_summary=incident_summary,
        affected_services=affected_services,
        key_metrics=key_metrics,
        important_events=important_events,
        documentation_findings=documentation_findings,
        historical_patterns=historical_patterns,
        owners_and_escalation=owners_and_escalation,
        open_questions=open_questions,
    )

    return ContextBuilderOutput(
        request_id=payload.request_id,
        session_id=payload.session_id,
        user_id=payload.user_id,
        query=payload.query,
        incident_key=payload.incident_key,
        service_name=payload.service_name,
        investigation_scope=payload.investigation_scope,
        incident=payload.incident,
        services=services,
        evidence=evidence,
        docs=docs,
        historical_incidents=historical_incidents,
        session_history=payload.session_history,
        context_content=context_content,
        status=status,
    )


def build_context_builder_log(
    output: ContextBuilderOutput,
    *,
    raw_evidence_count: int,
    latency_ms: int,
    status: str,
) -> dict[str, str | int]:
    return {
        "agent": "ContextBuilderAgent",
        "raw_evidence_count": raw_evidence_count,
        "compressed_event_count": len(output.context_content.important_events),
        "doc_count": len(output.context_content.documentation_findings),
        "open_question_count": len(output.context_content.open_questions),
        "latency_ms": latency_ms,
        "status": status,
    }


def _build_incident_summary(payload: ContextBuilderInput, evidence: list[dict]) -> str:
    if payload.incident:
        summary = str(payload.incident.get("summary") or "").strip()
        title = str(payload.incident.get("title") or "").strip()
        if summary and title:
            return f"{title}: {summary}"
        if summary:
            return summary
        if title:
            return title

    if evidence:
        return f"Collected {len(evidence)} evidence events for analysis."

    return "Investigation context prepared from available sources."


def _build_affected_services(services: list[dict]) -> list[AffectedService]:
    out: list[AffectedService] = []
    for service in services:
        name = str(service.get("service_name") or service.get("name") or "").strip()
        if not name:
            continue
        out.append(
            AffectedService(
                service_name=name,
                tier=_to_optional_str(service.get("tier")),
                impact_type=_to_optional_str(service.get("impact_type")),
            )
        )
    return out


def _build_key_metrics(evidence: list[dict]) -> list[KeyMetric]:
    metrics: list[KeyMetric] = []
    for item in evidence:
        metric_name = _to_optional_str(item.get("metric_name"))
        event_time = _to_optional_str(item.get("event_time"))
        if not metric_name or not event_time:
            continue
        raw_value = item.get("metric_value")
        value = float(raw_value) if isinstance(raw_value, (int, float)) else None
        metrics.append(
            KeyMetric(
                metric_name=metric_name,
                value=value,
                unit=_to_optional_str(item.get("unit")),
                event_time=event_time,
            )
        )

    metrics.sort(key=lambda m: m.event_time, reverse=True)
    return metrics[:15]


def _build_important_events(evidence: list[dict]) -> list[ImportantEvent]:
    events: list[ImportantEvent] = []
    for item in evidence:
        event_time = _to_optional_str(item.get("event_time"))
        event_type = _to_optional_str(item.get("event_type"))
        if not event_time or not event_type:
            continue

        event_id = (
            str(item.get("id") or item.get("event_id") or "").strip() or event_time
        )
        event_text = (
            _to_optional_str(item.get("event_text")) or f"Event type: {event_type}"
        )
        events.append(
            ImportantEvent(
                event_id=event_id,
                event_type=event_type,
                event_time=event_time,
                event_text=event_text,
            )
        )

    events.sort(key=lambda e: e.event_time, reverse=True)
    return events[:15]


def _build_documentation_findings(docs: list[dict]) -> list[DocumentationFinding]:
    scored_docs = sorted(
        docs,
        key=lambda d: float(d.get("score") or 0.0),
        reverse=True,
    )

    findings: list[DocumentationFinding] = []
    for doc in scored_docs[:8]:
        doc_id = _to_optional_str(doc.get("doc_id")) or "unknown"
        category = _to_optional_str(doc.get("category")) or "unknown"
        source_file = _to_optional_str(doc.get("source_file")) or "unknown"
        finding = _to_optional_str(doc.get("content_snippet")) or "No snippet available"
        findings.append(
            DocumentationFinding(
                doc_id=doc_id,
                category=category,
                source_file=source_file,
                finding=finding,
            )
        )

    return findings


def _build_historical_patterns(
    historical_incidents: list[dict],
) -> list[HistoricalPattern]:
    patterns: list[HistoricalPattern] = []
    for incident in historical_incidents:
        incident_key = _to_optional_str(incident.get("incident_key"))
        if not incident_key:
            continue

        pattern = (
            _to_optional_str(incident.get("similarity_reason"))
            or _to_optional_str(incident.get("summary"))
            or _to_optional_str(incident.get("title"))
            or "Historical pattern identified"
        )
        patterns.append(
            HistoricalPattern(
                incident_key=incident_key,
                pattern=pattern,
                relevance=_derive_relevance(incident),
            )
        )

    return patterns


def _build_owners_and_escalation(services: list[dict]) -> list[OwnerEscalation]:
    by_service: dict[str, OwnerEscalation] = {}
    for service in services:
        service_name = _to_optional_str(
            service.get("service_name") or service.get("name")
        )
        if not service_name:
            continue

        owner = (
            _to_optional_str(service.get("owner_full_name"))
            or _to_optional_str(service.get("owner_name"))
            or _to_optional_str(service.get("owner_email"))
            or _to_optional_str(service.get("owner_username"))
            or _to_optional_str(service.get("owner"))
        )
        contacts: list[str] = []
        raw_contacts = service.get("escalation_contacts")
        if isinstance(raw_contacts, list):
            contacts.extend([str(c) for c in raw_contacts if str(c).strip()])
        contact_value = _to_optional_str(service.get("contact_value"))
        contact_name = _to_optional_str(service.get("name"))
        if contact_name and contact_value:
            contacts.append(f"{contact_name}: {contact_value}")
        elif contact_value:
            contacts.append(contact_value)

        current = by_service.get(service_name)
        if current is None:
            by_service[service_name] = OwnerEscalation(
                service_name=service_name,
                owner=owner,
                escalation_contacts=contacts,
            )
            continue

        merged_owner = current.owner or owner
        merged_contacts = current.escalation_contacts + contacts
        deduped_contacts: list[str] = []
        seen: set[str] = set()
        for value in merged_contacts:
            if value in seen:
                continue
            seen.add(value)
            deduped_contacts.append(value)
        by_service[service_name] = OwnerEscalation(
            service_name=service_name,
            owner=merged_owner,
            escalation_contacts=deduped_contacts,
        )

    return list(by_service.values())


def _build_open_questions(
    *,
    payload: ContextBuilderInput,
    incident_found: bool,
    evidence: list[dict],
    documentation_findings: list[DocumentationFinding],
    owners_and_escalation: list[OwnerEscalation],
) -> list[str]:
    questions: list[str] = []

    if (
        payload.incident_key
        and payload.investigation_scope
        in {
            InvestigationScope.INCIDENT,
            InvestigationScope.REPORT,
        }
        and not incident_found
    ):
        questions.append(
            f"Incident {payload.incident_key} was not found. Should another key be used?"
        )

    if len(evidence) < 2:
        questions.append(
            "Evidence is limited. Should more telemetry/events be fetched?"
        )

    if not documentation_findings:
        questions.append(
            "No relevant documentation findings were found. Expand docs search filters?"
        )

    missing_owner = any(item.owner is None for item in owners_and_escalation)
    missing_escalation = any(
        not item.escalation_contacts for item in owners_and_escalation
    )
    if owners_and_escalation and (missing_owner or missing_escalation):
        questions.append(
            "Owner or escalation details are incomplete for some impacted services."
        )

    if not owners_and_escalation and payload.service_name:
        questions.append(
            "Service ownership/escalation data is missing. Fetch owner/contact details?"
        )

    return questions


def _derive_relevance(incident: dict) -> PatternRelevance:
    if incident.get("severity") in {"SEV-1", "SEV-2", "critical", "high"}:
        return PatternRelevance.HIGH

    resolved_at = incident.get("resolved_at")
    if isinstance(resolved_at, str):
        try:
            resolved_dt = datetime.fromisoformat(resolved_at.replace("Z", "+00:00"))
            if (datetime.now(tz=resolved_dt.tzinfo) - resolved_dt).days < 30:
                return PatternRelevance.HIGH
        except ValueError:
            pass

    if incident.get("similarity_reason"):
        return PatternRelevance.MEDIUM

    return PatternRelevance.LOW


def _dedupe_services(services: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for service in services:
        name = _to_optional_str(service.get("service_name") or service.get("name"))
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(service)
    return out


def _dedupe_evidence(evidence: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for item in evidence:
        evidence_id = str(item.get("id") or item.get("event_id") or "").strip()
        if not evidence_id:
            # Keep records even without id, but avoid accidental collisions.
            evidence_id = (
                f"event-time:{item.get('event_time')}|type:{item.get('event_type')}"
            )
        if evidence_id in seen:
            continue
        seen.add(evidence_id)
        out.append(item)
    return out


def _dedupe_docs(docs: list[dict]) -> list[dict]:
    seen: set[tuple[str, str]] = set()
    out: list[dict] = []
    for doc in docs:
        doc_id = _to_optional_str(doc.get("doc_id")) or ""
        source = _to_optional_str(doc.get("source_file")) or ""
        signature = (doc_id, source)
        if signature in seen:
            continue
        seen.add(signature)
        out.append(doc)
    return out


def _dedupe_historical(historical_incidents: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for incident in historical_incidents:
        key = _to_optional_str(incident.get("incident_key"))
        if not key:
            continue
        normalized = key.upper()
        if normalized in seen:
            continue
        seen.add(normalized)
        out.append(incident)
    return out


def _is_fully_empty(
    payload: ContextBuilderInput,
    services: list[dict],
    evidence: list[dict],
    docs: list[dict],
    historical_incidents: list[dict],
) -> bool:
    return (
        payload.incident is None
        and not services
        and not evidence
        and not docs
        and not historical_incidents
        and not payload.session_history
    )


def _to_optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
