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
from app.contracts.orchestrator import InvestigationScope
from app.tools.agent_tools import (
    get_incident_by_key,
    get_incident_services,
    get_resolutions,
    get_service_dependencies,
    get_service_owner,
    get_similar_incidents,
    search_docs,
)

AGENT_NAME = "IncidentAnalysisAgent"
INCIDENT_ANALYSIS_PROMPT = """
You are IncidentAnalysisAgent.
Return IncidentAnalysisOutput JSON only.
Input-handoff rule:
- Use ContextBuilderOutput from the latest prior stage as the source of truth.
Use only provided evidence from incident/events/docs/services.
Do not present assumptions as facts.
For each hypothesis:
- `supporting_evidence_refs` must reference real ids from provided data.
- `reasoning_summary` must clearly distinguish evidence-backed statements vs inference.
If certainty is low or evidence is missing, keep confidence low and include missing_information.
If uncertain, say "we don't have knowledge about this".
Do not emit markdown/code fences.
Never output placeholder text like "already processed" or "no more outputs needed".
For each user turn, produce a complete analysis output.
For policy/runbook/postmortem/architecture guidance questions:
- do not force root-cause hypotheses
- keep hypotheses empty when the user asked for documentation summary/guidance
- mark status `complete` when documentation evidence is sufficient
""".strip()

incident_analysis_agent = build_stage_agent(
    name=AGENT_NAME,
    instruction=INCIDENT_ANALYSIS_PROMPT,
    tools=[
        get_incident_by_key,
        get_incident_services,
        get_resolutions,
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
    query_lower = payload.query.lower()
    docs_guidance_intent = any(
        token in query_lower
        for token in ("policy", "runbook", "postmortem", "architecture", "dependency")
    )
    if docs_guidance_intent and payload.docs:
        return IncidentAnalysisOutput(
            hypotheses=[],
            analysis_decision=AnalysisDecision.STOP,
            missing_information=[],
            confidence=0.75,
            status="complete",
            iteration_summaries=[
                IterationSummary(
                    iteration=1,
                    requested_additional_tools=[],
                    received_evidence_count=len(payload.docs),
                    confidence_delta=0.0,
                    decision=AnalysisDecision.STOP,
                )
            ],
        )

    if payload.investigation_scope == InvestigationScope.OWNERSHIP:
        owner_rows = [
            row
            for row in payload.services
            if any(row.get(k) for k in ("owner_name", "owner_username", "owner_email"))
        ]
        if owner_rows:
            primary = owner_rows[0]
            owner_label = (
                str(primary.get("owner_name") or "").strip()
                or str(primary.get("owner_username") or "").strip()
                or str(primary.get("owner_email") or "").strip()
                or "unknown owner"
            )
            service_label = str(primary.get("service_name") or "service").strip()
            hypothesis = AnalysisHypothesis(
                cause=f"Ownership for {service_label} is assigned to {owner_label}.",
                confidence=0.8,
                supporting_evidence_refs=[f"service:{service_label}"],
                counter_evidence_refs=[],
                reasoning_summary="Ownership answer is derived from retrieved service-owner metadata.",
            )
            return IncidentAnalysisOutput(
                hypotheses=[hypothesis],
                analysis_decision=AnalysisDecision.STOP,
                missing_information=[],
                confidence=hypothesis.confidence,
                status="complete",
                iteration_summaries=[
                    IterationSummary(
                        iteration=1,
                        requested_additional_tools=[],
                        received_evidence_count=0,
                        confidence_delta=0.0,
                        decision=AnalysisDecision.STOP,
                    )
                ],
            )

        return IncidentAnalysisOutput(
            hypotheses=[],
            analysis_decision=AnalysisDecision.INCONCLUSIVE,
            missing_information=[
                "we don't have knowledge about this: missing ownership metadata"
            ],
            confidence=0.0,
            status="inconclusive",
            iteration_summaries=[
                IterationSummary(
                    iteration=1,
                    requested_additional_tools=[],
                    received_evidence_count=0,
                    confidence_delta=0.0,
                    decision=AnalysisDecision.INCONCLUSIVE,
                )
            ],
        )

    try:
        return await run_json_stage_with_timeout(
            agent=incident_analysis_agent,
            payload=payload,
            output_model=IncidentAnalysisOutput,
            user_id=str(payload.session_id),
            timeout_seconds=45,
        )
    except Exception:
        pass

    hypotheses: list[AnalysisHypothesis] = []
    resolution_row = next(
        (
            row
            for row in payload.evidence
            if any(
                str(row.get(k) or "").strip()
                for k in ("root_cause", "root_cause_summary")
            )
        ),
        None,
    )
    if resolution_row is not None:
        root_cause = (
            str(resolution_row.get("root_cause") or "").strip()
            or str(resolution_row.get("root_cause_summary") or "").strip()
        )
        ref = str(
            resolution_row.get("id")
            or resolution_row.get("resolution_id")
            or payload.incident.get("incident_key")
            if payload.incident
            else "resolution-record"
        )
        hypotheses.append(
            AnalysisHypothesis(
                cause=root_cause,
                confidence=0.85,
                supporting_evidence_refs=[f"resolution:{ref}"],
                counter_evidence_refs=[],
                reasoning_summary="Root cause extracted from retrieved resolution records.",
            )
        )
    elif payload.evidence or payload.docs:
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

    missing_information: list[str] = []
    if payload.investigation_scope == InvestigationScope.COMPARISON:
        if not payload.historical_incidents:
            missing_information.append(
                "we don't have knowledge about this: missing similar incidents"
            )
    elif payload.investigation_scope in {
        InvestigationScope.INCIDENT,
        InvestigationScope.REPORT,
    }:
        if not (payload.incident or payload.evidence or payload.docs):
            missing_information.append(
                "we don't have knowledge about this: missing incident evidence"
            )
    elif payload.investigation_scope == InvestigationScope.SERVICE:
        if not (payload.services or payload.docs or payload.evidence):
            missing_information.append(
                "we don't have knowledge about this: missing service metadata"
            )

    if not hypotheses and not missing_information:
        missing_information.append(
            "we don't have knowledge about this: insufficient evidence"
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
