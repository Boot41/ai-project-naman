from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from enum import Enum
from time import perf_counter
from typing import Any, Callable
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.agents.context_builder_agent import context_builder_with_adk_or_fallback
from app.agents.incident_analysis_agent import analysis_with_adk_or_fallback
from app.agents.response_composer_agent import composer_with_adk_or_fallback
from app.contracts.context_builder import ContextBuilderInput
from app.contracts.incident_analysis import IncidentAnalysisInput, LoopRuntimePolicy
from app.contracts.orchestrator import OrchestratorInput
from app.contracts.response_composer import ComposerInput, OutputStatus
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
from app.tools.contracts import make_error_response, make_no_data_response

logger = logging.getLogger(__name__)
ToolFn = Callable[..., dict[str, Any]]
_INCIDENT_KEY_PATTERN = re.compile(r"\bINC-(?:\d{4}-\d{4}|\d+)\b", re.IGNORECASE)
_SERVICE_PATTERN = re.compile(r"\b([a-z0-9-]+-service)\b", re.IGNORECASE)


class PipelineErrorCode(str, Enum):
    INCIDENT_NOT_FOUND = "INCIDENT_NOT_FOUND"
    RETRIEVAL_TIMEOUT = "RETRIEVAL_TIMEOUT"
    TOOL_EXECUTION_FAILED = "TOOL_EXECUTION_FAILED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class PipelineErrorPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = Field(pattern="^(error|not_found|inconclusive)$")
    error_code: PipelineErrorCode
    message: str = Field(min_length=1)
    next_action: str = Field(min_length=1)


@dataclass(frozen=True)
class PipelineRuntimePolicy:
    global_request_timeout_seconds: int = 420
    analysis: LoopRuntimePolicy = LoopRuntimePolicy()


class InvestigationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_id: str
    status: str
    output: dict | None = None
    error: PipelineErrorPayload | None = None
    logs: list[dict] = Field(default_factory=list)
    persistence: dict | None = None


async def run_investigation_pipeline(
    *,
    request_id: str,
    session_id: str,
    user_id: int,
    query: str,
    incident_key: str | None = None,
    service_name: str | None = None,
    policy: PipelineRuntimePolicy = PipelineRuntimePolicy(),
) -> InvestigationResult:
    trace_id = str(uuid4())
    logs: list[dict] = []
    try:
        session_uuid = UUID(session_id)
    except ValueError:
        return _error_result(
            trace_id=trace_id,
            logs=logs,
            code=PipelineErrorCode.TOOL_EXECUTION_FAILED,
            status="error",
            message="invalid session_id format; expected UUID string",
            next_action="retry with a valid session_id UUID",
        )

    async def _run() -> InvestigationResult:
        try:
            from app.agents.orchestrator_agent import orchestrate_with_adk_or_fallback

            seed_incident_key, seed_service_name, history_rows = (
                _resolve_context_seed_from_history(
                    session_id=str(session_uuid),
                    query=query,
                    incident_key=incident_key,
                    service_name=service_name,
                )
            )

            start = perf_counter()
            orchestrator_output = await orchestrate_with_adk_or_fallback(
                OrchestratorInput(
                    request_id=request_id,
                    session_id=session_uuid,
                    user_id=user_id,
                    query=query,
                    incident_key=seed_incident_key,
                    service_name=seed_service_name,
                )
            )
            logs.append(
                _step_log(
                    trace_id=trace_id,
                    request_id=request_id,
                    session_id=str(session_uuid),
                    user_id=user_id,
                    agent="OpsCopilotOrchestratorAgent",
                    step="orchestrator",
                    status="success",
                    latency_ms=_elapsed_ms(start),
                )
            )

            start = perf_counter()
            merged = await _fan_out_retrieval(
                [item.model_dump() for item in orchestrator_output.tool_plan]
            )
            merged["session_history"] = _merge_unique_records(
                history_rows, merged["session_history"]
            )
            if (
                orchestrator_output.investigation_scope.value == "ownership"
                and orchestrator_output.context_seed.incident_key
            ):
                _enrich_services_with_owner_escalation(
                    services=merged["services"],
                    incident_key=orchestrator_output.context_seed.incident_key,
                    service_name=orchestrator_output.context_seed.service_name,
                )
            _backfill_service_owners(services=merged["services"])
            logs.append(
                _step_log(
                    trace_id=trace_id,
                    request_id=request_id,
                    session_id=str(session_uuid),
                    user_id=user_id,
                    agent="RetrievalExecutor",
                    step="retrieval_fanout_merge",
                    status="success",
                    latency_ms=_elapsed_ms(start),
                )
            )

            incident_row = merged["incident"][0] if merged["incident"] else None
            if not _minimum_evidence_threshold(
                incident=incident_row,
                evidence=merged["evidence"],
                services=merged["services"],
                historical_incidents=merged["historical_incidents"],
                resolutions=merged["resolutions"],
                docs=merged["docs"],
            ):
                return _error_result(
                    trace_id=trace_id,
                    logs=logs,
                    code=PipelineErrorCode.INSUFFICIENT_EVIDENCE,
                    status="inconclusive",
                    message="we don't have knowledge about this",
                    next_action="provide more incident details and retry",
                )

            start = perf_counter()
            context_out = await context_builder_with_adk_or_fallback(
                ContextBuilderInput(
                    request_id=request_id,
                    session_id=session_uuid,
                    user_id=user_id,
                    query=query,
                    incident_key=orchestrator_output.context_seed.incident_key,
                    service_name=orchestrator_output.context_seed.service_name,
                    investigation_scope=orchestrator_output.investigation_scope,
                    incident=incident_row,
                    services=merged["services"],
                    evidence=merged["evidence"],
                    docs=merged["docs"],
                    historical_incidents=merged["historical_incidents"],
                    session_history=merged["session_history"],
                ),
            )
            logs.append(
                _step_log(
                    trace_id=trace_id,
                    request_id=request_id,
                    session_id=str(session_uuid),
                    user_id=user_id,
                    agent="ContextBuilderAgent",
                    step="context_builder",
                    status="success",
                    latency_ms=_elapsed_ms(start),
                )
            )

            if context_out.status == "not_found":
                return _error_result(
                    trace_id=trace_id,
                    logs=logs,
                    code=PipelineErrorCode.INCIDENT_NOT_FOUND,
                    status="not_found",
                    message="we don't have knowledge about this",
                    next_action="verify incident key and retry",
                )

            start = perf_counter()
            merged_services = list(context_out.services)
            merged_evidence = list(context_out.evidence)
            merged_docs = list(context_out.docs)
            merged_historical = list(context_out.historical_incidents)
            analysis_out = None

            for iteration in range(1, policy.analysis.max_iterations + 1):
                analysis_out = await analysis_with_adk_or_fallback(
                    IncidentAnalysisInput(
                        request_id=request_id,
                        session_id=session_uuid,
                        query=query,
                        investigation_scope=orchestrator_output.investigation_scope,
                        context_content=context_out.context_content,
                        incident=context_out.incident,
                        services=merged_services,
                        evidence=merged_evidence,
                        docs=merged_docs,
                        historical_incidents=merged_historical,
                        session_history=context_out.session_history,
                    ),
                    policy=policy.analysis,
                )
                if analysis_out.analysis_decision.value != "continue":
                    break

                followup_plan = _build_followup_plan(
                    missing_information=analysis_out.missing_information,
                    incident_key=orchestrator_output.context_seed.incident_key,
                    service_name=orchestrator_output.context_seed.service_name,
                    query=query,
                )
                if not followup_plan:
                    break
                followup = await _fan_out_retrieval(followup_plan)
                merged_services = _merge_unique_records(
                    merged_services, followup["services"]
                )
                merged_evidence = _merge_unique_records(
                    merged_evidence, followup["evidence"]
                )
                merged_docs = _merge_unique_records(merged_docs, followup["docs"])
                merged_historical = _merge_unique_records(
                    merged_historical, followup["historical_incidents"]
                )
                logs.append(
                    _step_log(
                        trace_id=trace_id,
                        request_id=request_id,
                        session_id=str(session_uuid),
                        user_id=user_id,
                        agent="IncidentAnalysisAgent",
                        step=f"analysis_loop_iteration_{iteration}",
                        status="continue",
                        latency_ms=0,
                        confidence=analysis_out.confidence,
                        evidence_refs=analysis_out.hypotheses[
                            0
                        ].supporting_evidence_refs
                        if analysis_out.hypotheses
                        else [],
                    )
                )

            if analysis_out is None:
                raise RuntimeError("IncidentAnalysisAgent returned no output")

            logs.append(
                _step_log(
                    trace_id=trace_id,
                    request_id=request_id,
                    session_id=str(session_uuid),
                    user_id=user_id,
                    agent="IncidentAnalysisAgent",
                    step="analysis",
                    status="success",
                    latency_ms=_elapsed_ms(start),
                    confidence=analysis_out.confidence,
                    evidence_refs=analysis_out.hypotheses[0].supporting_evidence_refs
                    if analysis_out.hypotheses
                    else [],
                )
            )

            if analysis_out.status == "inconclusive" and not analysis_out.hypotheses:
                return _error_result(
                    trace_id=trace_id,
                    logs=logs,
                    code=PipelineErrorCode.INSUFFICIENT_EVIDENCE,
                    status="inconclusive",
                    message="we don't have knowledge about this",
                    next_action="provide more evidence and retry",
                )

            start = perf_counter()
            composed = await composer_with_adk_or_fallback(
                ComposerInput(
                    request_id=request_id,
                    session_id=session_uuid,
                    query=query,
                    investigation_scope=orchestrator_output.investigation_scope,
                    context_content=context_out.context_content,
                    hypotheses=analysis_out.hypotheses,
                    confidence=analysis_out.confidence,
                    status=OutputStatus.INCONCLUSIVE
                    if analysis_out.status == "inconclusive"
                    else OutputStatus.COMPLETE,
                )
            )
            logs.append(
                {
                    "agent": "ResponseComposerAgent",
                    "output_status": composed.status.value,
                    "hypothesis_count": len(composed.hypotheses),
                    "evidence_count": len(composed.evidence),
                    "latency_ms": _elapsed_ms(start),
                    "status": "success",
                }
            )

            return InvestigationResult(
                trace_id=trace_id,
                status=composed.status.value,
                output=composed.model_dump(),
                error=None,
                logs=logs,
                persistence=None,
            )
        except Exception as exc:
            logger.exception("pipeline_unhandled_error trace_id=%s", trace_id)
            return _error_result(
                trace_id=trace_id,
                logs=logs,
                code=PipelineErrorCode.TOOL_EXECUTION_FAILED,
                status="error",
                message=f"we don't have knowledge about this: {exc}",
                next_action="retry later",
            )

    try:
        return await asyncio.wait_for(
            _run(), timeout=policy.global_request_timeout_seconds
        )
    except asyncio.TimeoutError:
        return _error_result(
            trace_id=trace_id,
            logs=logs,
            code=PipelineErrorCode.RETRIEVAL_TIMEOUT,
            status="error",
            message="we don't have knowledge about this",
            next_action="retry with a specific incident or service",
        )


async def _fan_out_retrieval(
    tool_plan: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    results = await asyncio.gather(*[_run_plan_item(item) for item in tool_plan])
    merged: dict[str, list[dict[str, Any]]] = {
        "incident": [],
        "services": [],
        "evidence": [],
        "docs": [],
        "historical_incidents": [],
        "resolutions": [],
        "session_history": [],
    }
    for tool_name, payload in results:
        if not payload.get("ok", False):
            continue
        data = payload.get("data", [])
        if not isinstance(data, list):
            data = [data]
        if tool_name == "get_incident_by_key":
            merged["incident"].extend(data)
        elif tool_name in {
            "get_incident_services",
            "get_service_owner",
            "get_service_dependencies",
            "get_escalation_contacts",
        }:
            merged["services"].extend(data)
        elif tool_name == "get_incident_evidence":
            merged["evidence"].extend(data)
        elif tool_name == "get_similar_incidents":
            merged["historical_incidents"].extend(data)
        elif tool_name == "get_resolutions":
            merged["resolutions"].extend(data)
            merged["evidence"].extend(data)
        elif tool_name == "load_session_messages":
            merged["session_history"].extend(data)
        elif tool_name == "search_docs":
            merged["docs"].extend(data)
    return merged


async def _run_plan_item(item: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    tool_name = str(item.get("tool"))
    args = item.get("args", {}) if isinstance(item.get("args", {}), dict) else {}
    fn = _tool_registry().get(tool_name)
    if fn is None:
        return tool_name, make_no_data_response(tool_name).model_dump()
    if any(str(v).startswith("$from_incident_services") for v in args.values()):
        return tool_name, make_no_data_response(tool_name).model_dump()
    cleaned_args = {k: v for k, v in args.items() if v is not None}
    try:
        return tool_name, fn(**cleaned_args)
    except TypeError:
        # ADK planner can emit incomplete args for some tools; skip safely.
        return tool_name, make_no_data_response(tool_name).model_dump()
    except Exception as exc:
        return tool_name, make_error_response(
            tool_name, "TOOL_EXECUTION_FAILED", str(exc)
        ).model_dump()


def _tool_registry() -> dict[str, ToolFn]:
    return {
        "get_incident_by_key": get_incident_by_key,
        "get_incident_services": get_incident_services,
        "get_incident_evidence": get_incident_evidence,
        "get_service_owner": get_service_owner,
        "get_service_dependencies": get_service_dependencies,
        "get_similar_incidents": get_similar_incidents,
        "get_resolutions": get_resolutions,
        "get_escalation_contacts": get_escalation_contacts,
        "load_session_messages": load_session_messages,
        "search_docs": search_docs,
    }


def _minimum_evidence_threshold(
    *,
    incident: dict | None,
    evidence: list[dict],
    services: list[dict],
    historical_incidents: list[dict],
    resolutions: list[dict],
    docs: list[dict],
) -> bool:
    return bool(
        (incident and evidence)
        or services
        or (historical_incidents and resolutions)
        or docs
    )


def _build_followup_plan(
    *,
    missing_information: list[str],
    incident_key: str | None,
    service_name: str | None,
    query: str,
) -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = []
    msg = " ".join(missing_information).lower()
    if ("incident" in msg or "evidence" in msg) and incident_key:
        plan.append(
            {
                "tool": "get_incident_evidence",
                "args": {"incident_key": incident_key, "limit": 200},
            }
        )
    if ("historical" in msg or "similar" in msg) and incident_key:
        plan.append(
            {
                "tool": "get_similar_incidents",
                "args": {"incident_key": incident_key},
            }
        )
    if ("service" in msg or "dependency" in msg) and service_name:
        plan.append(
            {
                "tool": "get_service_dependencies",
                "args": {"service_name": service_name},
            }
        )
    if "documentation" in msg or "docs" in msg:
        plan.append(
            {
                "tool": "search_docs",
                "args": {
                    "query": query,
                    "top_k": 5,
                    "category": None,
                    "service": service_name,
                },
            }
        )
    return plan


def _merge_unique_records(base: list[dict], incoming: list[dict]) -> list[dict]:
    if not incoming:
        return base
    out = list(base)
    seen = {_record_signature(item) for item in out}
    for item in incoming:
        signature = _record_signature(item)
        if signature in seen:
            continue
        seen.add(signature)
        out.append(item)
    return out


def _record_signature(item: dict) -> str:
    for key in ("id", "event_id", "doc_id", "incident_key", "service_name"):
        value = item.get(key)
        if value:
            return f"{key}:{value}"
    return str(sorted(item.items()))


def _error_result(
    *,
    trace_id: str,
    logs: list[dict],
    code: PipelineErrorCode,
    status: str,
    message: str,
    next_action: str,
) -> InvestigationResult:
    return InvestigationResult(
        trace_id=trace_id,
        status=status,
        output=None,
        error=PipelineErrorPayload(
            status=status,
            error_code=code,
            message=message,
            next_action=next_action,
        ),
        logs=logs,
        persistence=None,
    )


def _resolve_context_seed_from_history(
    *,
    session_id: str,
    query: str,
    incident_key: str | None,
    service_name: str | None,
) -> tuple[str | None, str | None, list[dict[str, Any]]]:
    resolved_incident = (incident_key or "").strip().upper() or _extract_incident_key(query)
    resolved_service = (service_name or "").strip().lower() or _extract_service_name(query)
    session_history: list[dict[str, Any]] = []

    if resolved_incident and resolved_service:
        return resolved_incident, resolved_service, session_history

    history_response = load_session_messages(session_id=session_id, limit=30)
    if not history_response.get("ok", False):
        return resolved_incident, resolved_service, session_history
    rows = history_response.get("data", [])
    if not isinstance(rows, list):
        return resolved_incident, resolved_service, session_history
    session_history = [row for row in rows if isinstance(row, dict)]

    for row in reversed(session_history):
        content_text = str(row.get("content_text") or "")
        structured = row.get("structured_json")

        if not resolved_incident:
            resolved_incident = _extract_incident_key(content_text) or _extract_from_any(
                structured, _INCIDENT_KEY_PATTERN
            )

        if not resolved_service:
            resolved_service = _extract_service_name(content_text) or _extract_from_any(
                structured, _SERVICE_PATTERN, group=1
            )

        if resolved_incident and resolved_service:
            break

    return resolved_incident, resolved_service, session_history


def _extract_incident_key(text: str) -> str | None:
    match = _INCIDENT_KEY_PATTERN.search(text)
    return match.group(0).upper() if match else None


def _extract_service_name(text: str) -> str | None:
    match = _SERVICE_PATTERN.search(text)
    return match.group(1).lower() if match else None


def _extract_from_any(
    value: Any, pattern: re.Pattern[str], *, group: int = 0, max_nodes: int = 600
) -> str | None:
    queue: list[Any] = [value]
    visited = 0
    while queue and visited < max_nodes:
        node = queue.pop(0)
        visited += 1
        if isinstance(node, str):
            match = pattern.search(node)
            if match:
                return match.group(group)
            continue
        if isinstance(node, dict):
            queue.extend(node.values())
            continue
        if isinstance(node, list):
            queue.extend(node)
    return None


def _enrich_services_with_owner_escalation(
    *,
    services: list[dict[str, Any]],
    incident_key: str,
    service_name: str | None,
) -> None:
    targets: list[str] = []
    if service_name:
        targets.append(service_name)
    if not targets:
        by_incident = get_incident_services(incident_key=incident_key)
        rows = by_incident.get("data", []) if isinstance(by_incident, dict) else []
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict):
                    continue
                name = str(row.get("service_name") or "").strip().lower()
                if name:
                    targets.append(name)

    unique_targets = sorted(set(targets))
    if not unique_targets:
        return

    owner_rows: list[dict[str, Any]] = []
    escalation_map: dict[str, list[str]] = {}
    for target in unique_targets:
        owner_payload = get_service_owner(service_name=target)
        owner_data = owner_payload.get("data", []) if isinstance(owner_payload, dict) else []
        if isinstance(owner_data, list):
            for row in owner_data:
                if isinstance(row, dict):
                    owner_rows.append(dict(row))

        escalation_payload = get_escalation_contacts(service_name=target)
        escalation_data = (
            escalation_payload.get("data", []) if isinstance(escalation_payload, dict) else []
        )
        contacts: list[str] = []
        if isinstance(escalation_data, list):
            for row in escalation_data:
                if not isinstance(row, dict):
                    continue
                label = str(row.get("name") or "").strip()
                channel = str(row.get("contact_type") or "").strip()
                value = str(row.get("contact_value") or "").strip()
                if label and channel and value:
                    contacts.append(f"{label} ({channel}: {value})")
                elif label and value:
                    contacts.append(f"{label} ({value})")
                elif value:
                    contacts.append(value)
        if contacts:
            escalation_map[target] = contacts

    if not owner_rows and not escalation_map:
        return

    for owner in owner_rows:
        service = str(owner.get("service_name") or "").strip().lower()
        if service and escalation_map.get(service):
            owner["escalation_contacts"] = escalation_map[service]

    merged = _merge_unique_records(services, owner_rows)
    services.clear()
    services.extend(merged)


def _backfill_service_owners(*, services: list[dict[str, Any]]) -> None:
    if not services:
        return

    service_names = sorted(
        {
            str(row.get("service_name") or row.get("name") or "").strip().lower()
            for row in services
            if isinstance(row, dict)
        }
        - {""}
    )
    if not service_names:
        return

    owner_rows: list[dict[str, Any]] = []
    for service in service_names:
        has_owner = any(
            (
                str(row.get("service_name") or row.get("name") or "").strip().lower()
                == service
            )
            and any(
                row.get(k)
                for k in (
                    "owner",
                    "owner_name",
                    "owner_full_name",
                    "owner_username",
                    "owner_email",
                )
            )
            for row in services
            if isinstance(row, dict)
        )
        if has_owner:
            continue

        payload = get_service_owner(service_name=service)
        data = payload.get("data", []) if isinstance(payload, dict) else []
        if isinstance(data, list):
            owner_rows.extend(dict(item) for item in data if isinstance(item, dict))

    if not owner_rows:
        return

    merged = _merge_unique_records(services, owner_rows)
    services.clear()
    services.extend(merged)


def _elapsed_ms(start: float) -> int:
    return int((perf_counter() - start) * 1000)


def _step_log(
    *,
    trace_id: str,
    request_id: str,
    session_id: str,
    user_id: int,
    agent: str,
    step: str,
    status: str,
    latency_ms: int,
    confidence: float = 0.0,
    evidence_refs: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "trace_id": trace_id,
        "request_id": request_id,
        "session_id": session_id,
        "user_id": user_id,
        "agent": agent,
        "step": step,
        "status": status,
        "latency_ms": latency_ms,
        "input_tokens": 0,
        "output_tokens": 0,
        "confidence": confidence,
        "evidence_refs": evidence_refs or [],
    }
