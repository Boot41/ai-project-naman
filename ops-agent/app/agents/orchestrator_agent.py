from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from collections.abc import Awaitable
from concurrent.futures import TimeoutError as FutureTimeoutError
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from google.adk.agents import Agent
from google.adk.agents import LoopAgent
from google.adk.agents import SequentialAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from app.agents.context_builder_agent import context_builder_agent
from app.agents.incident_analysis_agent import incident_analysis_agent
from app.agents.response_composer_agent import response_composer_agent
from app.agents.runtime import build_stage_agent, run_json_stage_with_timeout
from app.contracts.incident_analysis import LoopRuntimePolicy
from app.contracts.investigation_result import (
    InvestigationResult,
    PipelineErrorCode,
    PipelineErrorPayload,
)
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
from app.services.enrichment import enrich_investigation_facts, enrich_owner_escalation
from app.services.output_normalizer import extract_json, normalize_composer_payload
from app.tools.agent_tools import (
    get_escalation_contacts,
    get_investigation_bundle,
    get_incident_by_key,
    get_incident_services,
    get_resolutions,
    get_service_dependencies,
    get_service_owner,
    get_similar_incidents,
    load_session_messages,
    search_docs,
)

logger = logging.getLogger(__name__)
AGENT_NAME = "OpsCopilotOrchestratorAgent"
FLOW_AGENT_NAME = "OpsCopilotInvestigationFlow"
ANALYSIS_LOOP_AGENT_NAME = "IncidentAnalysisLoopAgent"
OPSCOPILOT_PROMPT = """
You are OpsCopilotOrchestratorAgent, the root OpsCopilot ADK entry agent.
Your job is to produce OrchestratorOutput JSON only.
Plan retrieval tools for incident investigation and route to context_builder.
Handoff contract:
- output must include `context_seed` with best-known `incident_key` and `service_name`
- tools should prefer single bundled retrieval first for stability
Do not return markdown, prose, or wrapper keys.
Do not return code fences (no ``` blocks).
Never say work is already done/processed.
Every user turn must produce a fresh plan.
Do not answer from general knowledge.
Flow: user query -> orchestrator -> parallel retrieval -> context builder -> analysis(loop) -> response composer.
Tool-call policy (strict):
- Default first retrieval call should be `get_investigation_bundle` with query/session_id and any known incident/service.
- For policy/runbook/postmortem/architecture questions, set `docs_category` to one of:
  `policies`, `runbooks`, `postmortems`, `architecture`.
- Ownership query ("who owns ... escalation contacts"): call `get_service_owner` then `get_escalation_contacts` only.
- Root-cause query for a known incident key: call `get_incident_by_key` then `get_resolutions` only.
- Comparison query ("compare ... similar incidents"): call tools in this exact order:
  1) `get_similar_incidents` with args `{"incident_key": "<primary_incident_key>"}`
  2) `get_incident_by_key` for the primary incident
  3) `get_resolutions` for the primary incident
  4) `get_incident_by_key` for top similar incident
  5) `get_resolutions` for top similar incident
  For this first call, do NOT send `limit` or extra args.
- Do NOT call `get_incident_evidence` for the above intents.
""".strip()

_INCIDENT_KEY_IN_QUERY = re.compile(r"\bINC-(?:\d{4}-\d{4}|\d+)\b", re.IGNORECASE)
_SERVICE_IN_QUERY = re.compile(r"\b([a-z0-9-]+-service)\b", re.IGNORECASE)
_shared_session_service = InMemorySessionService()  # type: ignore[no-untyped-call]

orchestrator_agent = build_stage_agent(
    name=AGENT_NAME,
    instruction=OPSCOPILOT_PROMPT,
    tools=[
        get_investigation_bundle,
        get_incident_by_key,
        get_incident_services,
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
        adk_output = await run_json_stage_with_timeout(
            agent=orchestrator_agent,
            payload=payload,
            output_model=OrchestratorOutput,
            user_id=str(payload.user_id),
            timeout_seconds=45,
        )
        return _normalize_orchestrator_output(payload, adk_output)
    except Exception:
        return build_orchestrator_plan(payload)


def _normalize_orchestrator_output(
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
        has_incident_lookup = any(
            i.tool == "get_incident_by_key" for i in normalized_plan
        )
        has_resolution_lookup = any(
            i.tool == "get_resolutions" for i in normalized_plan
        )
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
    incident_key = (
        payload.incident_key or ""
    ).strip().upper() or _extract_incident_key(payload.query)
    service_name = (
        payload.service_name or ""
    ).strip().lower() or _extract_service_name(payload.query)

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


def _run_async(
    coro: Awaitable[InvestigationResult], *, timeout_seconds: float = 60.0
) -> InvestigationResult:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(asyncio.wait_for(coro, timeout=timeout_seconds))
    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(asyncio.run, coro).result(timeout=timeout_seconds)


def run_opscopilot_pipeline(
    query: str,
    request_id: str | None = None,
    incident_key: str | None = None,
    service_name: str | None = None,
    session_id: str | None = None,
    user_id: int = 1,
) -> dict:
    try:
        result = _run_async(
            run_investigation_via_root_agent(
                request_id=request_id or str(uuid4()),
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

# Graph-visible ADK flow for ADK Web: stage agents are first-class sub-agents.
analysis_loop_agent = LoopAgent(
    name=ANALYSIS_LOOP_AGENT_NAME,
    description="Loop analysis stage up to policy max iterations.",
    sub_agents=[incident_analysis_agent],
    max_iterations=LoopRuntimePolicy().max_iterations,
)

root_agent = SequentialAgent(
    name=FLOW_AGENT_NAME,
    description="Sequential OpsCopilot multi-agent flow graph.",
    sub_agents=[
        orchestrator_agent,
        context_builder_agent,
        analysis_loop_agent,
        response_composer_agent,
    ],
)


def get_configured_entry_agent() -> Agent:
    return root_agent


async def run_investigation_via_root_agent(
    *,
    request_id: str,
    session_id: str,
    user_id: int,
    query: str,
    incident_key: str | None = None,
    service_name: str | None = None,
) -> InvestigationResult:
    """
    Execute investigations through the ADK root agent graph.
    API and ADK Web both use the same root agent behavior.
    """
    trace_id = str(uuid4())
    settings = get_settings()
    if settings.google_api_key.strip():
        os.environ["GOOGLE_API_KEY"] = settings.google_api_key.strip()

    input_payload = {
        "request_id": request_id,
        "session_id": session_id,
        "user_id": user_id,
        "query": query,
        "incident_key": incident_key,
        "service_name": service_name,
    }
    prompt = (
        "Run complete OpsCopilot investigation flow.\n"
        "Return final ComposerOutput JSON only.\n"
        "Do not include markdown, code fences, or extra wrapper text.\n"
        f"INPUT_JSON:\n{json.dumps(input_payload, ensure_ascii=True)}"
    )
    try:
        user_id_str = str(user_id)
        session = await _shared_session_service.get_session(
            app_name=settings.app_name,
            user_id=user_id_str,
            session_id=session_id,
        )
        if session is None:
            session = await _shared_session_service.create_session(
                app_name=settings.app_name,
                user_id=user_id_str,
                session_id=session_id,
            )
        runner = Runner(
            agent=root_agent,
            app_name=settings.app_name,
            session_service=_shared_session_service,
        )
        content = types.Content(role="user", parts=[types.Part.from_text(text=prompt)])
        final_text = ""
        async for event in runner.run_async(
            user_id=user_id_str, session_id=session.id, new_message=content
        ):
            if event.is_final_response() and event.content and event.content.parts:
                final_text = event.content.parts[0].text or ""

        parsed = extract_json(final_text)
        if {"trace_id", "status", "output", "error", "logs", "persistence"} <= set(parsed):
            if isinstance(parsed.get("output"), dict):
                parsed["output"] = normalize_composer_payload(parsed["output"], query=query)
                enriched_output = await asyncio.to_thread(
                    enrich_owner_escalation,
                    parsed["output"],
                    incident_key,
                    str(parsed["output"].get("summary") or ""),
                )
                enriched_output = await asyncio.to_thread(
                    enrich_investigation_facts,
                    enriched_output,
                    query=query,
                    incident_key=incident_key,
                )
                parsed["output"] = normalize_composer_payload(enriched_output, query=query)
                parsed["status"] = str(parsed["output"].get("status") or parsed.get("status") or "complete")
            return InvestigationResult.model_validate(parsed)

        if isinstance(parsed, dict) and parsed.get("summary"):
            normalized_output = normalize_composer_payload(parsed, query=query)
            enriched_output = await asyncio.to_thread(
                enrich_owner_escalation,
                normalized_output,
                incident_key,
                str(normalized_output.get("summary") or ""),
            )
            enriched_output = await asyncio.to_thread(
                enrich_investigation_facts,
                enriched_output,
                query=query,
                incident_key=incident_key,
            )
            normalized_output = normalize_composer_payload(enriched_output, query=query)
            status = str(normalized_output.get("status") or parsed.get("status") or "complete")
            return InvestigationResult(
                trace_id=trace_id,
                status=status,
                output=normalized_output,
                error=None,
                logs=[],
                persistence=None,
            )

        return _root_error(
            trace_id=trace_id,
            message="we don't have knowledge about this",
            next_action="retry with a more specific incident/service query",
        )
    except Exception as exc:
        logger.exception("root_agent_execution_failed request_id=%s", request_id)
        return _root_error(
            trace_id=trace_id,
            message=f"we don't have knowledge about this: {exc}",
            next_action="retry with a narrower query",
        )


def _root_error(*, trace_id: str, message: str, next_action: str) -> InvestigationResult:
    return InvestigationResult(
        trace_id=trace_id,
        status="error",
        output=None,
        error=PipelineErrorPayload(
            status="error",
            error_code=PipelineErrorCode.TOOL_EXECUTION_FAILED,
            message=message,
            next_action=next_action,
        ),
        logs=[],
        persistence=None,
    )
