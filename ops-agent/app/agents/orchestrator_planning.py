from __future__ import annotations

import re

from app.contracts.orchestrator import (
    ContextSeed,
    InvestigationScope,
    OrchestratorInput,
    OrchestratorOutput,
    RoutingTarget,
    ToolPlanItem,
    ToolPriority,
)

_INCIDENT_KEY_IN_QUERY = re.compile(r"\bINC-(?:\d{4}-\d{4}|\d+)\b", re.IGNORECASE)
_SERVICE_IN_QUERY = re.compile(r"\b([a-z0-9-]+-service)\b", re.IGNORECASE)


def normalize_orchestrator_output(
    payload: OrchestratorInput, output: OrchestratorOutput
) -> OrchestratorOutput:
    service_name = (
        output.context_seed.service_name
        or (payload.service_name or "").strip().lower()
        or _extract_service_name(payload.query)
    )
    incident_key = (
        output.context_seed.incident_key
        or (payload.incident_key or "").strip().upper()
        or _extract_incident_key(payload.query)
    )

    docs_category = _resolve_docs_category(payload.query)
    normalized_plan: list[ToolPlanItem] = []
    for item in output.tool_plan:
        args = {k: v for k, v in item.args.items() if v is not None}
        if item.tool == "get_investigation_bundle":
            if not args.get("docs_category") and docs_category:
                args["docs_category"] = docs_category
        if item.tool in {
            "get_service_owner",
            "get_service_dependencies",
            "get_escalation_contacts",
        }:
            if not args.get("service_name") and service_name:
                args["service_name"] = service_name
        elif item.tool in {
            "get_incident_by_key",
            "get_incident_services",
            "get_similar_incidents",
            "get_resolutions",
        }:
            if not args.get("incident_key") and incident_key:
                args["incident_key"] = incident_key
        normalized_plan.append(item.model_copy(update={"args": args}))

    if (
        output.investigation_scope == InvestigationScope.OWNERSHIP
        and service_name
        and not any(
            i.tool in {"get_service_owner", "get_escalation_contacts"}
            for i in normalized_plan
        )
    ):
        normalized_plan.extend(
            [
                ToolPlanItem(
                    tool="get_service_owner",
                    args={"service_name": service_name},
                    priority=ToolPriority.HIGH,
                    reason="Resolve service ownership.",
                ),
                ToolPlanItem(
                    tool="get_escalation_contacts",
                    args={"service_name": service_name},
                    priority=ToolPriority.HIGH,
                    reason="Resolve escalation contacts.",
                ),
            ]
        )

    if (
        output.investigation_scope == InvestigationScope.OWNERSHIP
        and incident_key
        and not service_name
        and not any(i.tool == "get_incident_services" for i in normalized_plan)
    ):
        normalized_plan.append(
            ToolPlanItem(
                tool="get_incident_services",
                args={"incident_key": incident_key},
                priority=ToolPriority.HIGH,
                reason="Resolve impacted services before ownership lookup.",
            )
        )

    if incident_key:
        has_incident_lookup = any(i.tool == "get_incident_by_key" for i in normalized_plan)
        has_resolution_lookup = any(i.tool == "get_resolutions" for i in normalized_plan)
        if not has_incident_lookup:
            normalized_plan.append(
                ToolPlanItem(
                    tool="get_incident_by_key",
                    args={"incident_key": incident_key},
                    priority=ToolPriority.HIGH,
                    reason="Load incident record.",
                )
            )
        if not has_resolution_lookup:
            normalized_plan.append(
                ToolPlanItem(
                    tool="get_resolutions",
                    args={"incident_key": incident_key},
                    priority=ToolPriority.HIGH,
                    reason="Load root cause and resolution details.",
                )
            )

    return output.model_copy(
        update={
            "tool_plan": normalized_plan,
            "context_seed": output.context_seed.model_copy(
                update={"service_name": service_name, "incident_key": incident_key}
            ),
        }
    )


def build_orchestrator_plan(payload: OrchestratorInput) -> OrchestratorOutput:
    incident_key = (payload.incident_key or "").strip().upper() or _extract_incident_key(payload.query)
    service_name = (payload.service_name or "").strip().lower() or _extract_service_name(payload.query)

    lowered = payload.query.lower()
    docs_category = _resolve_docs_category(payload.query)
    scope = InvestigationScope.SERVICE
    if incident_key or any(k in lowered for k in ["incident", "outage", "root cause"]):
        scope = InvestigationScope.INCIDENT
    elif any(k in lowered for k in ["report", "full report"]):
        scope = InvestigationScope.REPORT
    elif any(k in lowered for k in ["similar", "compare", "historical"]):
        scope = InvestigationScope.COMPARISON
    elif any(k in lowered for k in ["owner", "ownership", "escalation", "on-call"]):
        scope = InvestigationScope.OWNERSHIP

    plan: list[ToolPlanItem] = [
        ToolPlanItem(
            tool="get_investigation_bundle",
            args={
                "query": payload.query,
                "session_id": str(payload.session_id),
                "incident_key": incident_key or None,
                "service_name": service_name or None,
                "docs_category": docs_category,
                "top_k_docs": 5,
            },
            priority=ToolPriority.HIGH,
            reason="Fetch merged retrieval context in one tool call for lower latency and stable handoff.",
        ),
    ]

    if incident_key:
        plan.extend(
            [
                ToolPlanItem(
                    tool="get_incident_by_key",
                    args={"incident_key": incident_key},
                    priority=ToolPriority.HIGH,
                    reason="Load incident record.",
                ),
                ToolPlanItem(
                    tool="get_incident_services",
                    args={"incident_key": incident_key},
                    priority=ToolPriority.HIGH,
                    reason="Load impacted services.",
                ),
                ToolPlanItem(
                    tool="get_similar_incidents",
                    args={"incident_key": incident_key},
                    priority=ToolPriority.MEDIUM,
                    reason="Load similar incidents.",
                ),
                ToolPlanItem(
                    tool="get_resolutions",
                    args={"incident_key": incident_key},
                    priority=ToolPriority.MEDIUM,
                    reason="Load previous resolutions.",
                ),
            ]
        )

    if service_name:
        plan.extend(
            [
                ToolPlanItem(
                    tool="get_service_owner",
                    args={"service_name": service_name},
                    priority=ToolPriority.HIGH,
                    reason="Resolve service ownership.",
                ),
                ToolPlanItem(
                    tool="get_escalation_contacts",
                    args={"service_name": service_name},
                    priority=ToolPriority.HIGH,
                    reason="Resolve escalation contacts.",
                ),
                ToolPlanItem(
                    tool="get_service_dependencies",
                    args={"service_name": service_name},
                    priority=ToolPriority.MEDIUM,
                    reason="Load service dependencies.",
                ),
            ]
        )

    seen: set[tuple[str, str]] = set()
    deduped: list[ToolPlanItem] = []
    for item in plan:
        key = (item.tool, str(sorted(item.args.items())))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)

    return OrchestratorOutput(
        investigation_scope=scope,
        routing_target=RoutingTarget.CONTEXT_BUILDER,
        tool_plan=deduped,
        context_seed=ContextSeed(
            request_id=payload.request_id,
            session_id=payload.session_id,
            user_id=payload.user_id,
            query=payload.query,
            incident_key=incident_key,
            service_name=service_name,
        ),
    )


def _extract_incident_key(query: str) -> str | None:
    match = _INCIDENT_KEY_IN_QUERY.search(query)
    return match.group(0).upper() if match else None


def _extract_service_name(query: str) -> str | None:
    match = _SERVICE_IN_QUERY.search(query)
    return match.group(1).lower() if match else None


def _resolve_docs_category(query: str) -> str | None:
    lowered = query.lower()
    if "policy" in lowered:
        return "policies"
    if "runbook" in lowered:
        return "runbooks"
    if "postmortem" in lowered:
        return "postmortems"
    if "architecture" in lowered or "dependency" in lowered:
        return "architecture"
    return None
