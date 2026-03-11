from __future__ import annotations

from google.adk.agents import Agent

from app.agents.runtime import build_stage_agent, run_json_stage_with_timeout
from app.contracts.incident_analysis import (
    AnalysisDecision,
    AnalysisHypothesis,
    IncidentAnalysisInput,
    IncidentAnalysisOutput,
    IterationSummary,
    LoopRuntimePolicy,
)
from app.tools.agent_tools import (
    get_incident_evidence,
    get_service_dependencies,
    get_service_owner,
    get_similar_incidents,
    search_docs,
)

AGENT_NAME = "IncidentAnalysisAgent"
INCIDENT_ANALYSIS_PROMPT = """
You are IncidentAnalysisAgent.
Return IncidentAnalysisOutput JSON only.
Use only provided evidence. If uncertain, say "we don't have knowledge about this".
""".strip()

incident_analysis_agent = build_stage_agent(
    name=AGENT_NAME,
    instruction=INCIDENT_ANALYSIS_PROMPT,
    tools=[
        get_incident_evidence,
        get_service_dependencies,
        get_service_owner,
        get_similar_incidents,
        search_docs,
    ],
)


def build_incident_analysis_agent() -> Agent:
    return incident_analysis_agent


async def analysis_with_adk_or_fallback(
    payload: IncidentAnalysisInput,
    *,
    policy: LoopRuntimePolicy | None = None,
) -> IncidentAnalysisOutput:
    try:
        return await run_json_stage_with_timeout(
            agent=incident_analysis_agent,
            payload=payload,
            output_model=IncidentAnalysisOutput,
            user_id=str(payload.session_id),
            timeout_seconds=120,
        )
    except Exception:
        pass

    missing_information = [
        msg
        for msg in [
            "we don't have knowledge about this: missing incident evidence"
            if not payload.evidence
            else "",
            "we don't have knowledge about this: missing service metadata"
            if not payload.services
            else "",
            "we don't have knowledge about this: missing documentation evidence"
            if not payload.docs
            else "",
        ]
        if msg
    ]
    hypotheses: list[AnalysisHypothesis] = []
    if payload.evidence or payload.docs:
        source = payload.evidence[0] if payload.evidence else payload.docs[0]
        hypotheses.append(
            AnalysisHypothesis(
                cause="Preliminary pattern from available data",
                confidence=0.55,
                supporting_evidence_refs=[
                    str(
                        source.get("id")
                        or source.get("event_id")
                        or source.get("doc_id")
                        or "unknown-ref"
                    )
                ],
                counter_evidence_refs=[],
                reasoning_summary="Fallback analysis using currently retrieved context.",
            )
        )

    decision = (
        AnalysisDecision.INCONCLUSIVE if missing_information else AnalysisDecision.STOP
    )
    status = "inconclusive" if missing_information else "complete"
    return IncidentAnalysisOutput(
        hypotheses=hypotheses,
        analysis_decision=decision,
        missing_information=missing_information,
        confidence=max((h.confidence for h in hypotheses), default=0.0),
        status=status,
        iteration_summaries=[
            IterationSummary(
                iteration=1,
                requested_additional_tools=[],
                received_evidence_count=len(payload.evidence),
                confidence_delta=0.0,
                decision=decision,
            )
        ],
    )
