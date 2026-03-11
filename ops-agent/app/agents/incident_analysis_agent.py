from __future__ import annotations

from datetime import UTC, datetime
from typing import Callable

from google.adk.agents import Agent

from app.agents.runtime import (
    build_stage_agent,
    ensure_adk_key_configured,
    run_json_stage,
)
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

INCIDENT_ANALYSIS_PROMPT = """
<!--
agent_name: IncidentAnalysisAgent
version: 1.0.0
last_updated: 2026-03-11
owner: ops-agent
-->

You are IncidentAnalysisAgent.

Task:
- Produce evidence-backed hypotheses with confidence in [0,1].
- Include supporting_evidence_refs and counter_evidence_refs.
- Decide one of: continue|stop|inconclusive.
- Provide missing_information list.

Allowed tools:
- get_incident_evidence
- get_service_dependencies
- get_service_owner
- get_similar_incidents
- search_docs

Rules:
- No speculation without evidence refs.
- Every hypothesis must have at least one supporting ref.
- If documentation findings are present, create at least one docs-backed hypothesis using doc refs.
- For service troubleshooting queries with relevant docs, do not return inconclusive unless docs conflict or are empty.
- If required data is missing, request additional tool calls instead of guessing.
- If evidence is insufficient, set decision to continue or inconclusive based on context.
- If root cause cannot be determined, state: "Root cause undetermined with current evidence."
- Never invent incidents, services, owners, or metrics.
- If information is missing, explicitly state "insufficient information".
- Provide concrete, operator-ready reasoning from retrieved docs (not meta advice like "review docs").
- Output strict JSON only matching IncidentAnalysisOutput schema.
""".strip()

AdditionalRetrievalFn = Callable[[list[str], int], dict[str, list[dict]]]


def build_incident_analysis_agent() -> Agent:
    return build_stage_agent(
        name="IncidentAnalysisAgent",
        instruction=INCIDENT_ANALYSIS_PROMPT,
        tools=[
            get_incident_evidence,
            get_service_dependencies,
            get_service_owner,
            get_similar_incidents,
            search_docs,
        ],
    )


async def analysis_with_adk_or_fallback(
    payload: IncidentAnalysisInput,
    *,
    policy: LoopRuntimePolicy | None = None,
) -> IncidentAnalysisOutput:
    ensure_adk_key_configured()
    effective_policy = policy or LoopRuntimePolicy()
    try:
        best: IncidentAnalysisOutput | None = None
        for _iteration in range(effective_policy.max_iterations):
            candidate = await run_json_stage(
                agent=build_incident_analysis_agent(),
                payload=payload,
                output_model=IncidentAnalysisOutput,
                user_id=str(payload.session_id),
            )
            if _prefer_fallback_analysis(candidate, payload):
                break
            best = candidate
            if candidate.analysis_decision.value != "continue":
                break

        if best is None:
            raise RuntimeError("ADK analysis returned no output")
        return best
    except Exception:
        return run_incident_analysis(payload, policy=effective_policy)


def run_incident_analysis(
    payload: IncidentAnalysisInput,
    *,
    policy: LoopRuntimePolicy = LoopRuntimePolicy(),
    additional_retrieval_fn: AdditionalRetrievalFn | None = None,
) -> IncidentAnalysisOutput:
    evidence = list(payload.evidence)
    services = list(payload.services)
    docs = list(payload.docs)
    historical_incidents = list(payload.historical_incidents)

    start = datetime.now(tz=UTC)
    previous_confidence = 0.0
    iteration_summaries: list[IterationSummary] = []

    final_hypotheses: list[AnalysisHypothesis] = []
    final_missing_information: list[str] = []
    final_decision = AnalysisDecision.INCONCLUSIVE

    for iteration in range(1, policy.max_iterations + 1):
        elapsed = (datetime.now(tz=UTC) - start).total_seconds()
        if elapsed >= policy.analysis_total_budget_seconds:
            break

        hypotheses, counter_refs = _build_hypotheses(
            evidence=evidence, docs=docs, historical=historical_incidents
        )
        final_hypotheses = hypotheses

        confidence = max((h.confidence for h in hypotheses), default=0.0)
        final_missing_information = _detect_missing_information(
            services=services,
            evidence=evidence,
            docs=docs,
            historical=historical_incidents,
            counter_refs=counter_refs,
        )

        decision = _decide(
            confidence=confidence,
            hypothesis_support_count=max(
                (len(h.supporting_evidence_refs) for h in hypotheses), default=0
            ),
            missing_information=final_missing_information,
            iteration=iteration,
            elapsed_seconds=elapsed,
            policy=policy,
        )

        requested_tools: list[str] = []
        if decision == AnalysisDecision.CONTINUE and additional_retrieval_fn:
            requested_tools = _select_additional_tools(
                missing_information=final_missing_information,
                max_calls=policy.max_additional_tool_calls_per_iteration,
            )
            additional = additional_retrieval_fn(final_missing_information, iteration)
            evidence.extend(additional.get("evidence", []))
            services.extend(additional.get("services", []))
            docs.extend(additional.get("docs", []))
            historical_incidents.extend(additional.get("historical_incidents", []))

        iteration_summaries.append(
            IterationSummary(
                iteration=iteration,
                requested_additional_tools=requested_tools,
                received_evidence_count=len(evidence),
                confidence_delta=round(confidence - previous_confidence, 4),
                decision=decision,
            )
        )
        previous_confidence = confidence
        final_decision = decision

        if decision in {AnalysisDecision.STOP, AnalysisDecision.INCONCLUSIVE}:
            break

    final_confidence = max((h.confidence for h in final_hypotheses), default=0.0)
    status = "complete" if final_decision == AnalysisDecision.STOP else "inconclusive"

    return IncidentAnalysisOutput(
        hypotheses=final_hypotheses,
        analysis_decision=final_decision,
        missing_information=final_missing_information,
        confidence=final_confidence,
        status=status,
        iteration_summaries=iteration_summaries,
    )


def build_incident_analysis_log(
    *,
    iteration: int,
    requested_additional_tools: list[str],
    received_evidence_count: int,
    best_confidence: float,
    decision: AnalysisDecision,
    latency_ms: int,
    status: str,
) -> dict[str, str | int | float | list[str]]:
    return {
        "agent": "IncidentAnalysisAgent",
        "iteration": iteration,
        "requested_additional_tools": requested_additional_tools,
        "received_evidence_count": received_evidence_count,
        "best_confidence": round(best_confidence, 4),
        "decision": decision.value,
        "latency_ms": latency_ms,
        "status": status,
    }


def _build_hypotheses(
    *,
    evidence: list[dict],
    docs: list[dict],
    historical: list[dict],
) -> tuple[list[AnalysisHypothesis], list[str]]:
    if not evidence:
        if not docs:
            return [], []
        doc_refs = _doc_supporting_refs(docs)
        doc_cause = _infer_doc_cause(docs)
        doc_confidence = _score_confidence(
            support_count=len(doc_refs),
            has_docs=True,
            has_historical=bool(historical),
            counter_count=0,
        )
        hypothesis = AnalysisHypothesis(
            cause=doc_cause,
            confidence=max(0.76, doc_confidence),
            supporting_evidence_refs=doc_refs,
            counter_evidence_refs=[],
            reasoning_summary="Cause inferred from runbook/postmortem documentation findings.",
        )
        return [hypothesis], []

    primary = evidence[0]
    support_refs = _supporting_refs(evidence)
    counter_refs = _counter_evidence_refs(evidence)
    cause = _infer_cause(primary, docs)
    confidence = _score_confidence(
        support_count=len(support_refs),
        has_docs=bool(docs),
        has_historical=bool(historical),
        counter_count=len(counter_refs),
    )

    hypothesis = AnalysisHypothesis(
        cause=cause,
        confidence=confidence,
        supporting_evidence_refs=support_refs,
        counter_evidence_refs=counter_refs,
        reasoning_summary="Cause inferred from incident metrics/events and corroborating context.",
    )
    return [hypothesis], counter_refs


def _infer_cause(primary_event: dict, docs: list[dict]) -> str:
    metric_name = str(primary_event.get("metric_name") or "").lower()
    event_text = str(primary_event.get("event_text") or "").lower()

    if "latency" in metric_name or "latency" in event_text:
        return "Latency spike in critical request path"
    if "error" in metric_name or "error" in event_text:
        return "Elevated error-rate caused service instability"
    if docs:
        return "Operational failure pattern aligned with runbook/postmortem findings"
    return "Likely service degradation pattern"


def _infer_doc_cause(docs: list[dict]) -> str:
    text = " ".join(
        str(d.get("content_snippet") or d.get("finding") or "").lower()
        for d in docs[:5]
    )
    if "timeout" in text:
        return "Likely timeout-driven latency in payment request path"
    if "retry" in text:
        return "Retry amplification likely contributed to service latency"
    if "saturation" in text or "queue" in text:
        return "Capacity saturation likely causing increased latency"
    return "Operational failure pattern aligned with runbook/postmortem findings"


def _supporting_refs(evidence: list[dict]) -> list[str]:
    refs: list[str] = []
    for item in evidence:
        ref = str(item.get("id") or item.get("event_id") or "").strip()
        if ref and ref not in refs:
            refs.append(ref)
        if len(refs) >= 4:
            break
    if not refs:
        refs.append("event:unknown")
    return refs


def _doc_supporting_refs(docs: list[dict]) -> list[str]:
    refs: list[str] = []
    for item in docs:
        ref = str(item.get("doc_id") or item.get("id") or "").strip()
        if ref and ref not in refs:
            refs.append(ref)
        if len(refs) >= 4:
            break
    if not refs:
        refs.append("doc:unknown")
    return refs


def _counter_evidence_refs(evidence: list[dict]) -> list[str]:
    contradictory = {"recovered", "normal", "resolved", "decrease"}
    refs: list[str] = []
    for item in evidence:
        text = str(item.get("event_text") or "").lower()
        if any(token in text for token in contradictory):
            ref = str(item.get("id") or item.get("event_id") or "").strip()
            if ref and ref not in refs:
                refs.append(ref)
    return refs


def _score_confidence(
    *, support_count: int, has_docs: bool, has_historical: bool, counter_count: int
) -> float:
    score = 0.35
    score += min(0.3, 0.1 * support_count)
    if has_docs:
        score += 0.1
    if has_historical:
        score += 0.1
    score -= min(0.25, 0.08 * counter_count)
    return max(0.0, min(1.0, round(score, 3)))


def _detect_missing_information(
    *,
    services: list[dict],
    evidence: list[dict],
    docs: list[dict],
    historical: list[dict],
    counter_refs: list[str],
) -> list[str]:
    missing: list[str] = []

    if services and not any("depends_on_service_name" in item for item in services):
        missing.append("missing service dependency evidence")

    has_owner = any(
        (item.get("owner_full_name") or item.get("owner_username") or item.get("owner"))
        for item in services
    )
    has_escalation = any(bool(item.get("escalation_contacts")) for item in services)
    if services and (not has_owner or not has_escalation):
        missing.append("missing owner/escalation evidence")

    if not historical:
        missing.append("missing historical pattern support")

    if counter_refs:
        missing.append("conflicting event chronology")

    if len(evidence) < 2 and not docs:
        missing.append("insufficient evidence volume")

    if not docs:
        missing.append("documentation corroboration missing")

    return missing


def _decide(
    *,
    confidence: float,
    hypothesis_support_count: int,
    missing_information: list[str],
    iteration: int,
    elapsed_seconds: float,
    policy: LoopRuntimePolicy,
) -> AnalysisDecision:
    if confidence >= policy.target_confidence and hypothesis_support_count >= 2:
        return AnalysisDecision.STOP

    if (
        iteration >= policy.max_iterations
        or elapsed_seconds >= policy.analysis_total_budget_seconds
    ):
        return AnalysisDecision.INCONCLUSIVE

    useful_gaps = [
        gap
        for gap in missing_information
        if gap
        in {
            "missing service dependency evidence",
            "missing owner/escalation evidence",
            "missing historical pattern support",
            "conflicting event chronology",
            "insufficient evidence volume",
            "documentation corroboration missing",
        }
    ]
    if confidence < policy.target_confidence and useful_gaps:
        return AnalysisDecision.CONTINUE

    return AnalysisDecision.INCONCLUSIVE


def _select_additional_tools(
    *, missing_information: list[str], max_calls: int
) -> list[str]:
    mapping = {
        "missing service dependency evidence": "get_service_dependencies",
        "missing owner/escalation evidence": "get_service_owner",
        "missing historical pattern support": "get_similar_incidents",
        "conflicting event chronology": "get_incident_evidence",
        "insufficient evidence volume": "get_incident_evidence",
        "documentation corroboration missing": "search_docs",
    }

    tools: list[str] = []
    for gap in missing_information:
        tool = mapping.get(gap)
        if not tool or tool in tools:
            continue
        tools.append(tool)
        if len(tools) >= max_calls:
            break
    return tools


def _prefer_fallback_analysis(
    candidate: IncidentAnalysisOutput, payload: IncidentAnalysisInput
) -> bool:
    if not payload.docs:
        return False
    if candidate.status != "inconclusive":
        return False
    if candidate.confidence >= 0.75 and candidate.hypotheses:
        return False
    return True
