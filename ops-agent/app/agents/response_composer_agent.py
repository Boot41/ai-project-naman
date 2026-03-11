from __future__ import annotations

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

AGENT_NAME = "ResponseComposerAgent"
RESPONSE_COMPOSER_PROMPT = """
You are ResponseComposerAgent.
Return ComposerOutput JSON only with grounded evidence/actions.
If information is missing, explicitly state "insufficient information".
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
        return await run_json_stage_with_timeout(
            agent=response_composer_agent,
            payload=payload,
            output_model=ComposerOutput,
            user_id=str(payload.session_id),
            timeout_seconds=120,
        )
    except Exception:
        pass

    summary = (
        "Investigation is inconclusive due to insufficient information."
        if payload.status == OutputStatus.INCONCLUSIVE
        else (payload.context_content.incident_summary or "Investigation completed.")
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
        recommended_actions=(
            [f"Resolve gap: {q}" for q in payload.context_content.open_questions]
            if payload.context_content.open_questions
            else ["insufficient information: gather additional evidence and retry"]
        ),
        report=summary,
        status=payload.status,
    )
