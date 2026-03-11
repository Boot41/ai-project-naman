from __future__ import annotations

import asyncio
import os
import re
from concurrent.futures import TimeoutError as FutureTimeoutError
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from google.adk.agents import Agent

from app.agents.runtime import build_stage_agent, run_json_stage_with_timeout
from app.contracts.orchestrator import (
    ContextSeed,
    InvestigationScope,
    OrchestratorInput,
    OrchestratorOutput,
    RoutingTarget,
    ToolPlanItem,
    ToolPriority,
)
from app.core.config import get_settings
from app.investigation_flow import run_investigation_pipeline
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
    search_docs,
)

AGENT_NAME = "OpsCopilotOrchestratorAgent"
ORCHESTRATOR_PROMPT = """
You are OpsCopilotOrchestratorAgent.
Return OrchestratorOutput JSON only.
Plan retrieval tools for incident investigation and route to context_builder.
No hallucinations. If data is missing, state "insufficient information".
""".strip()

OPSCOPILOT_PROMPT = """
You are OpsCopilotOrchestratorAgent, the root OpsCopilot ADK entry agent.
You MUST call run_opscopilot_pipeline exactly once for every user investigation request.
Do not answer directly from general knowledge.
If tool output is inconclusive, return that output as-is and ask for more incident details.
Flow: user query -> orchestrator -> parallel retrieval -> context builder -> analysis(loop) -> response composer.
Return JSON only.
""".strip()

_INCIDENT_KEY_IN_QUERY = re.compile(r"\bINC-(?:\d{4}-\d{4}|\d+)\b", re.IGNORECASE)
_SERVICE_IN_QUERY = re.compile(r"\b([a-z0-9-]+-service)\b", re.IGNORECASE)

orchestrator_agent = build_stage_agent(
    name=AGENT_NAME,
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
        search_docs,
    ],
)


def build_orchestrator_agent() -> Agent:
    return orchestrator_agent


async def orchestrate_with_adk_or_fallback(
    payload: OrchestratorInput,
) -> OrchestratorOutput:
    try:
        return await run_json_stage_with_timeout(
            agent=orchestrator_agent,
            payload=payload,
            output_model=OrchestratorOutput,
            user_id=str(payload.user_id),
            timeout_seconds=120,
        )
    except Exception:
        return build_orchestrator_plan(payload)


def build_orchestrator_plan(payload: OrchestratorInput) -> OrchestratorOutput:
    incident_key = (payload.incident_key or "").strip().upper() or None
    if not incident_key:
        match = _INCIDENT_KEY_IN_QUERY.search(payload.query)
        incident_key = match.group(0).upper() if match else None

    service_name = (payload.service_name or "").strip().lower() or None
    if not service_name:
        match = _SERVICE_IN_QUERY.search(payload.query)
        service_name = match.group(1).lower() if match else None

    lowered = payload.query.lower()
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
            tool="load_session_messages",
            args={"session_id": str(payload.session_id), "limit": 30},
            priority=ToolPriority.HIGH,
            reason="Load prior conversation context.",
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
            reason="Retrieve runbook/postmortem/policy context.",
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
                    tool="get_incident_evidence",
                    args={"incident_key": incident_key, "limit": 200},
                    priority=ToolPriority.HIGH,
                    reason="Load incident evidence timeline.",
                ),
                ToolPlanItem(
                    tool="get_similar_incidents",
                    args={"incident_key": incident_key, "limit": 5},
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

    # lightweight dedupe by tool + args
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


def _run_async(coro: asyncio.Future, *, timeout_seconds: float = 60.0) -> object:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(asyncio.wait_for(coro, timeout=timeout_seconds))
    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(asyncio.run, coro).result(timeout=timeout_seconds)


def run_opscopilot_pipeline(
    query: str,
    incident_key: str | None = None,
    service_name: str | None = None,
    session_id: str | None = None,
    user_id: int = 1,
) -> dict:
    try:
        result = _run_async(
            run_investigation_pipeline(
                request_id=str(uuid4()),
                session_id=session_id or str(uuid4()),
                user_id=user_id,
                query=query,
                incident_key=incident_key,
                service_name=service_name,
            ),
            timeout_seconds=60.0,
        )
        return result.model_dump()
    except (TimeoutError, FutureTimeoutError):
        return {
            "trace_id": str(uuid4()),
            "status": "inconclusive",
            "output": None,
            "error": {
                "status": "inconclusive",
                "error_code": "TOOL_EXECUTION_FAILED",
                "message": "we don't have knowledge about this",
                "next_action": "retry with a narrower query",
            },
            "logs": [],
            "persistence": None,
        }


settings = get_settings()
if settings.google_api_key.strip():
    os.environ["GOOGLE_API_KEY"] = settings.google_api_key.strip()

root_agent = Agent(
    name=AGENT_NAME,
    model=settings.model_name,
    description="Root ADK orchestrator for the OpsCopilot investigation flow.",
    instruction=OPSCOPILOT_PROMPT,
    tools=[run_opscopilot_pipeline],
)
