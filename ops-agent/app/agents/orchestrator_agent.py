from __future__ import annotations

import re
from dataclasses import dataclass

from google.adk.agents import Agent

from app.contracts.orchestrator import (
    ContextSeed,
    InvestigationScope,
    OrchestratorInput,
    OrchestratorOutput,
    RoutingTarget,
    ToolPlanItem,
    ToolPriority,
)
from app.agents.runtime import (
    build_stage_agent,
    ensure_adk_key_configured,
    run_json_stage,
)
from app.tools.agent_tools import (
    get_escalation_contacts,
    get_incident_by_key,
    get_incident_evidence,
    get_incident_services,
    get_resolutions,
    get_service_dependencies,
    get_service_owner,
    get_similar_incidents,
    load_session_messages,
    save_assistant_message,
    search_docs,
)

ORCHESTRATOR_PROMPT = """
<!--
agent_name: OpsCopilotOrchestratorAgent
version: 1.0.0
last_updated: 2026-03-11
owner: ops-agent
-->

You are OpsCopilotOrchestratorAgent.

Task:
- Classify user intent into one scope: incident|service|ownership|comparison|report.
- Build deterministic tool_plan entries with tool, args, priority, reason.
- Set routing_target to context_builder.

Allowed tools:
- get_incident_by_key
- get_incident_services
- get_incident_evidence
- get_service_owner
- get_service_dependencies
- get_similar_incidents
- get_resolutions
- get_escalation_contacts
- load_session_messages
- save_assistant_message
- search_docs

Rules:
- Prefer scope priority: incident > report > comparison > ownership > service.
- If incident_key exists or appears in query, use incident scope.
- If required data is missing, request additional tool calls instead of guessing.
- Never invent incidents, services, owners, or metrics.
- If information is missing, explicitly state "insufficient information".
- Output strict JSON only matching OrchestratorOutput schema.
- Do not provide narrative text.
""".strip()

_INCIDENT_KEY_PATTERN = re.compile(r"\bINC-(?:\d{4}-\d{4}|\d+)\b", re.IGNORECASE)
_INCIDENT_VALIDATOR = re.compile(r"^INC-(?:\d{4}-\d{4}|\d+)$")
_SERVICE_NAME_PATTERN = re.compile(r"\b([a-z0-9-]+-service)\b", re.IGNORECASE)


@dataclass(frozen=True)
class ClassificationSignals:
    incident: bool
    report: bool
    comparison: bool
    ownership: bool
    service: bool


def build_orchestrator_agent() -> Agent:
    return build_stage_agent(
        name="OpsCopilotOrchestratorAgent",
        instruction=ORCHESTRATOR_PROMPT,
        tools=[
            get_incident_by_key,
            get_incident_services,
            get_incident_evidence,
            get_service_owner,
            get_service_dependencies,
            get_similar_incidents,
            get_resolutions,
            get_escalation_contacts,
            load_session_messages,
            save_assistant_message,
            search_docs,
        ],
    )


async def orchestrate_with_adk_or_fallback(
    payload: OrchestratorInput,
) -> OrchestratorOutput:
    ensure_adk_key_configured()
    try:
        return await run_json_stage(
            agent=build_orchestrator_agent(),
            payload=payload,
            output_model=OrchestratorOutput,
            user_id=str(payload.user_id),
        )
    except Exception:
        return build_orchestrator_plan(payload)


def build_orchestrator_plan(payload: OrchestratorInput) -> OrchestratorOutput:
    incident_key = _resolve_incident_key(payload)
    service_name = _resolve_service_name(payload)
    scope = _classify_scope(query=payload.query, incident_key=incident_key)
    tool_plan = _build_tool_plan(
        scope=scope,
        payload=payload,
        incident_key=incident_key,
        service_name=service_name,
    )

    context_seed = ContextSeed(
        request_id=payload.request_id,
        session_id=payload.session_id,
        user_id=payload.user_id,
        query=payload.query,
        incident_key=incident_key,
        service_name=service_name,
    )

    return OrchestratorOutput(
        investigation_scope=scope,
        routing_target=RoutingTarget.CONTEXT_BUILDER,
        tool_plan=tool_plan,
        context_seed=context_seed,
    )


def build_orchestrator_log(
    output: OrchestratorOutput, latency_ms: int, status: str
) -> dict[str, str | int]:
    return {
        "agent": "OpsCopilotOrchestratorAgent",
        "scope": output.investigation_scope.value,
        "routing_target": output.routing_target.value,
        "tool_count": len(output.tool_plan),
        "latency_ms": latency_ms,
        "status": status,
    }


def _resolve_incident_key(payload: OrchestratorInput) -> str | None:
    if payload.incident_key:
        key = payload.incident_key.upper().strip()
        if not _INCIDENT_VALIDATOR.match(key):
            raise ValueError(
                "incident_key must match legacy INC-123 or canonical INC-2026-0001"
            )
        return key

    match = _INCIDENT_KEY_PATTERN.search(payload.query)
    if not match:
        return None
    return match.group(0).upper()


def _classify_scope(query: str, incident_key: str | None) -> InvestigationScope:
    lowered = query.lower()
    signals = ClassificationSignals(
        incident=incident_key is not None
        or any(
            word in lowered
            for word in ["incident", "outage", "root cause", "what happened"]
        ),
        report=any(
            word in lowered for word in ["report", "full report", "generate report"]
        ),
        comparison=any(
            word in lowered
            for word in ["similar", "compare", "comparison", "historical"]
        ),
        ownership=any(
            word in lowered
            for word in ["owner", "owns", "ownership", "on-call", "escalation"]
        ),
        service=any(
            word in lowered
            for word in ["service", "dependency", "dependencies", "health"]
        ),
    )

    if signals.incident:
        return InvestigationScope.INCIDENT
    if signals.report:
        return InvestigationScope.REPORT
    if signals.comparison:
        return InvestigationScope.COMPARISON
    if signals.ownership:
        return InvestigationScope.OWNERSHIP
    if signals.service:
        return InvestigationScope.SERVICE

    return InvestigationScope.SERVICE


def _resolve_service_name(payload: OrchestratorInput) -> str | None:
    if payload.service_name:
        return payload.service_name.strip().lower()
    match = _SERVICE_NAME_PATTERN.search(payload.query)
    if not match:
        return None
    return match.group(1).lower()


def _build_tool_plan(
    scope: InvestigationScope,
    payload: OrchestratorInput,
    incident_key: str | None,
    service_name: str | None,
) -> list[ToolPlanItem]:
    items: list[ToolPlanItem] = [
        ToolPlanItem(
            tool="load_session_messages",
            args={"session_id": str(payload.session_id), "limit": 30},
            priority=ToolPriority.HIGH,
            reason="Load recent conversation context for continuity.",
        )
    ]

    if (
        scope in {InvestigationScope.INCIDENT, InvestigationScope.REPORT}
        and incident_key
    ):
        items.extend(
            [
                ToolPlanItem(
                    tool="get_incident_by_key",
                    args={"incident_key": incident_key},
                    priority=ToolPriority.HIGH,
                    reason="Fetch incident record for investigation grounding.",
                ),
                ToolPlanItem(
                    tool="get_incident_services",
                    args={"incident_key": incident_key},
                    priority=ToolPriority.HIGH,
                    reason="Identify impacted services for blast-radius analysis.",
                ),
                ToolPlanItem(
                    tool="get_incident_evidence",
                    args={"incident_key": incident_key, "limit": 200},
                    priority=ToolPriority.HIGH,
                    reason="Gather incident evidence timeline and metrics.",
                ),
                ToolPlanItem(
                    tool="get_similar_incidents",
                    args={"incident_key": incident_key, "limit": 5},
                    priority=ToolPriority.MEDIUM,
                    reason="Retrieve historical comparables for pattern matching.",
                ),
                ToolPlanItem(
                    tool="get_resolutions",
                    args={"incident_key": incident_key},
                    priority=ToolPriority.MEDIUM,
                    reason="Collect past resolution/root-cause context.",
                ),
                ToolPlanItem(
                    tool="search_docs",
                    args={
                        "query": payload.query,
                        "top_k": 5,
                        "category": None,
                        "service": service_name,
                    },
                    priority=ToolPriority.MEDIUM,
                    reason="Pull supporting runbook/postmortem/policy evidence.",
                ),
            ]
        )

    if scope in {
        InvestigationScope.OWNERSHIP,
        InvestigationScope.SERVICE,
        InvestigationScope.REPORT,
    }:
        service_arg = service_name or "$from_incident_services.service_name"
        items.extend(
            [
                ToolPlanItem(
                    tool="get_service_owner",
                    args={"service_name": service_arg},
                    priority=ToolPriority.HIGH,
                    reason="Resolve service ownership for actionability.",
                ),
                ToolPlanItem(
                    tool="get_escalation_contacts",
                    args={"service_name": service_arg},
                    priority=ToolPriority.HIGH,
                    reason="Resolve escalation path for incident handling.",
                ),
                ToolPlanItem(
                    tool="get_service_dependencies",
                    args={"service_name": service_arg},
                    priority=ToolPriority.MEDIUM,
                    reason="Map dependency graph for failure propagation.",
                ),
            ]
        )

    if scope in {
        InvestigationScope.SERVICE,
        InvestigationScope.COMPARISON,
        InvestigationScope.OWNERSHIP,
        InvestigationScope.REPORT,
        InvestigationScope.INCIDENT,
    }:
        docs_category = None
        if scope == InvestigationScope.COMPARISON:
            docs_category = "postmortems"
        if scope == InvestigationScope.INCIDENT and not incident_key:
            docs_category = "postmortems"
        items.append(
            ToolPlanItem(
                tool="search_docs",
                args={
                    "query": payload.query,
                    "top_k": 5,
                    "category": docs_category,
                    "service": service_name,
                },
                priority=ToolPriority.MEDIUM,
                reason="Retrieve relevant docs for operational context.",
            )
        )

    # Deterministic de-duplication by serialized key.
    seen: set[tuple[str, str]] = set()
    deduped: list[ToolPlanItem] = []
    for item in items:
        signature = (item.tool, str(sorted(item.args.items())))
        if signature in seen:
            continue
        seen.add(signature)
        deduped.append(item)

    return deduped
