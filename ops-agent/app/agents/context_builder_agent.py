from __future__ import annotations

from google.adk.agents import Agent

from app.agents.runtime import build_stage_agent, run_json_stage_with_timeout
from app.contracts.context_builder import (
    AffectedService,
    ContextBuilderInput,
    ContextBuilderOutput,
    ContextContent,
    DocumentationFinding,
    HistoricalPattern,
    ImportantEvent,
    OwnerEscalation,
    PatternRelevance,
)
from app.contracts.orchestrator import InvestigationScope

AGENT_NAME = "ContextBuilderAgent"
CONTEXT_BUILDER_PROMPT = """
You are ContextBuilderAgent.
Transform retrieval outputs into ContextBuilderOutput JSON only.
Do not invent facts. If data is missing, say "insufficient information" in open_questions.
""".strip()

context_builder_agent = build_stage_agent(
    name=AGENT_NAME,
    instruction=CONTEXT_BUILDER_PROMPT,
    tools=[],
)


def build_context_builder_agent() -> Agent:
    return context_builder_agent


async def context_builder_with_adk_or_fallback(
    payload: ContextBuilderInput,
) -> ContextBuilderOutput:
    try:
        return await run_json_stage_with_timeout(
            agent=context_builder_agent,
            payload=payload,
            output_model=ContextBuilderOutput,
            user_id=str(payload.user_id),
            timeout_seconds=120,
        )
    except Exception:
        pass

    status = "in_progress"
    if (
        payload.investigation_scope
        in {InvestigationScope.INCIDENT, InvestigationScope.REPORT}
        and payload.incident_key
        and payload.incident is None
    ):
        status = "not_found"

    return ContextBuilderOutput(
        request_id=payload.request_id,
        session_id=payload.session_id,
        user_id=payload.user_id,
        query=payload.query,
        incident_key=payload.incident_key,
        service_name=payload.service_name,
        investigation_scope=payload.investigation_scope,
        incident=payload.incident,
        services=payload.services,
        evidence=payload.evidence,
        docs=payload.docs,
        historical_incidents=payload.historical_incidents,
        session_history=payload.session_history,
        context_content=ContextContent(
            incident_summary=(
                str((payload.incident or {}).get("summary") or "").strip()
                or str((payload.incident or {}).get("title") or "").strip()
                or "Investigation context assembled from retrieved data."
            ),
            affected_services=[
                AffectedService(
                    service_name=str(
                        item.get("service_name") or item.get("name") or "unknown"
                    )
                )
                for item in payload.services[:20]
            ],
            key_metrics=[],
            important_events=[
                ImportantEvent(
                    event_id=str(item.get("id") or item.get("event_id") or f"evt-{i}"),
                    event_type=str(item.get("event_type") or "event"),
                    event_time=str(item.get("event_time") or "unknown"),
                    event_text=str(item.get("event_text") or "No event text available"),
                )
                for i, item in enumerate(payload.evidence[:15], start=1)
            ],
            documentation_findings=[
                DocumentationFinding(
                    doc_id=str(item.get("doc_id") or f"doc-{i}"),
                    category=str(item.get("category") or "unknown"),
                    source_file=str(item.get("source_file") or "unknown"),
                    finding=str(item.get("content_snippet") or "No snippet available"),
                )
                for i, item in enumerate(payload.docs[:8], start=1)
            ],
            historical_patterns=[
                HistoricalPattern(
                    incident_key=str(item.get("incident_key") or f"hist-{i}"),
                    pattern=str(
                        item.get("similarity_reason")
                        or "Historical similarity observed"
                    ),
                    relevance=PatternRelevance.MEDIUM,
                )
                for i, item in enumerate(payload.historical_incidents[:5], start=1)
            ],
            owners_and_escalation=[
                OwnerEscalation(
                    service_name=str(
                        item.get("service_name") or item.get("name") or "unknown"
                    ),
                    owner=(
                        str(item.get("owner") or "").strip()
                        or str(item.get("owner_full_name") or "").strip()
                        or str(item.get("owner_username") or "").strip()
                        or None
                    ),
                    escalation_contacts=[
                        str(contact).strip()
                        for contact in (item.get("escalation_contacts") or [])
                        if str(contact).strip()
                    ],
                )
                for item in payload.services[:20]
            ],
            open_questions=[
                q
                for q in [
                    "insufficient information: missing incident evidence"
                    if not payload.evidence
                    else "",
                    "insufficient information: missing documentation evidence"
                    if not payload.docs
                    else "",
                    "insufficient information: missing service metadata"
                    if not payload.services
                    else "",
                ]
                if q
            ],
        ),
        status=status,
    )
