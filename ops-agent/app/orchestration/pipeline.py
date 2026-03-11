from __future__ import annotations

import asyncio
import logging
from time import perf_counter
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.agents import (
    analysis_with_adk_or_fallback,
    build_persistence_payload,
    build_response_composer_log,
    composer_with_adk_or_fallback,
    context_builder_with_adk_or_fallback,
    orchestrate_with_adk_or_fallback,
)
from app.contracts.context_builder import ContextBuilderInput
from app.contracts.incident_analysis import IncidentAnalysisInput
from app.contracts.orchestrator import OrchestratorInput
from app.contracts.response_composer import ComposerInput, OutputStatus
from app.orchestration.errors import PipelineErrorCode, PipelineErrorPayload
from app.orchestration.logging import build_step_log
from app.orchestration.persistence import InMemoryPersistenceGateway
from app.orchestration.retrieval import RetrievalExecutor
from app.orchestration.runtime_policy import PipelineRuntimePolicy

logger = logging.getLogger(__name__)


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
    retrieval_executor: RetrievalExecutor | None = None,
    persistence_gateway: InMemoryPersistenceGateway | None = None,
    policy: PipelineRuntimePolicy = PipelineRuntimePolicy(),
) -> InvestigationResult:
    trace_id = str(uuid4())
    logs: list[dict] = []
    session_uuid = UUID(session_id)
    logger.info(
        "pipeline_start trace_id=%s request_id=%s session_id=%s user_id=%s query=%s",
        trace_id,
        request_id,
        session_uuid,
        user_id,
        query[:160],
    )

    retrieval = retrieval_executor or RetrievalExecutor()
    persistence = persistence_gateway or InMemoryPersistenceGateway()

    async def _run() -> InvestigationResult:
        try:
            start = perf_counter()
            logger.info("pipeline_step_start trace_id=%s step=orchestrator", trace_id)
            orchestrator_input = OrchestratorInput(
                request_id=request_id,
                session_id=session_uuid,
                user_id=user_id,
                query=query,
                incident_key=incident_key,
                service_name=service_name,
            )
            orchestrator_output = await orchestrate_with_adk_or_fallback(
                orchestrator_input
            )
            logs.append(
                build_step_log(
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
            logger.info("pipeline_step_start trace_id=%s step=retrieval_fanout_merge", trace_id)
            merged = await retrieval.fan_out(
                [item.model_dump() for item in orchestrator_output.tool_plan]
            )
            logs.append(
                build_step_log(
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
                docs=merged["docs"],
                historical_incidents=merged["historical_incidents"],
                resolutions=merged["resolutions"],
            ):
                logger.warning(
                    "pipeline_step_insufficient_evidence trace_id=%s incident=%s evidence=%s services=%s docs=%s historical=%s resolutions=%s",
                    trace_id,
                    bool(incident_row),
                    len(merged["evidence"]),
                    len(merged["services"]),
                    len(merged["docs"]),
                    len(merged["historical_incidents"]),
                    len(merged["resolutions"]),
                )
                return _error_result(
                    trace_id=trace_id,
                    logs=logs,
                    code=PipelineErrorCode.INSUFFICIENT_EVIDENCE,
                    status="inconclusive",
                    message="Insufficient evidence to run analysis.",
                    next_action="Fetch additional incident/service/docs evidence and retry.",
                )

            start = perf_counter()
            logger.info("pipeline_step_start trace_id=%s step=context_builder", trace_id)
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
                build_step_log(
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
                    message="Requested incident was not found.",
                    next_action="Verify the incident key and retry.",
                )

            start = perf_counter()
            logger.info("pipeline_step_start trace_id=%s step=analysis_loop", trace_id)
            analysis_out = await analysis_with_adk_or_fallback(
                IncidentAnalysisInput(
                    request_id=request_id,
                    session_id=session_uuid,
                    query=query,
                    investigation_scope=orchestrator_output.investigation_scope,
                    context_content=context_out.context_content,
                    incident=context_out.incident,
                    services=context_out.services,
                    evidence=context_out.evidence,
                    docs=context_out.docs,
                    historical_incidents=context_out.historical_incidents,
                    session_history=context_out.session_history,
                ),
                policy=policy.analysis,
            )
            evidence_refs = []
            if analysis_out.hypotheses:
                evidence_refs = analysis_out.hypotheses[0].supporting_evidence_refs
            logs.append(
                build_step_log(
                    trace_id=trace_id,
                    request_id=request_id,
                    session_id=str(session_uuid),
                    user_id=user_id,
                    agent="IncidentAnalysisAgent",
                    step="analysis_loop",
                    status="success",
                    latency_ms=_elapsed_ms(start),
                    confidence=analysis_out.confidence,
                    evidence_refs=evidence_refs,
                )
            )

            start = perf_counter()
            logger.info("pipeline_step_start trace_id=%s step=response_composer", trace_id)
            composer_status = OutputStatus.COMPLETE
            if analysis_out.status == "inconclusive":
                composer_status = OutputStatus.INCONCLUSIVE

            composed = await composer_with_adk_or_fallback(
                ComposerInput(
                    request_id=request_id,
                    session_id=session_uuid,
                    query=query,
                    investigation_scope=orchestrator_output.investigation_scope,
                    context_content=context_out.context_content,
                    hypotheses=analysis_out.hypotheses,
                    confidence=analysis_out.confidence,
                    status=composer_status,
                )
            )
            logs.append(
                build_response_composer_log(
                    output=composed,
                    latency_ms=_elapsed_ms(start),
                    status="success",
                )
            )

            start = perf_counter()
            logger.info("pipeline_step_start trace_id=%s step=persistence", trace_id)
            persist_payload = build_persistence_payload(composed)
            message_id = persistence.save_assistant_message(
                session_id=session_uuid,
                content_text=str(persist_payload["content_text"]),
                structured_json=persist_payload["structured_json"],
            )
            refs = (
                composed.hypotheses[0].supporting_evidence_refs
                if composed.hypotheses
                else []
            )
            persistence.save_investigation_evidence(
                session_id=session_uuid,
                message_id=message_id,
                evidence_refs=refs,
            )
            persistence.update_session_last_activity(session_id=session_uuid)
            logs.append(
                build_step_log(
                    trace_id=trace_id,
                    request_id=request_id,
                    session_id=str(session_uuid),
                    user_id=user_id,
                    agent="PersistenceNode",
                    step="persistence",
                    status="success",
                    latency_ms=_elapsed_ms(start),
                )
            )

            result = InvestigationResult(
                trace_id=trace_id,
                status=composed.status.value,
                output=composed.model_dump(),
                error=None,
                logs=logs,
                persistence={"message_id": message_id},
            )
            logger.info(
                "pipeline_done trace_id=%s status=%s message_id=%s",
                trace_id,
                result.status,
                message_id,
            )
            return result
        except ValueError as exc:
            logger.exception(
                "pipeline_schema_validation_error trace_id=%s error=%s",
                trace_id,
                exc,
            )
            return _error_result(
                trace_id=trace_id,
                logs=logs,
                code=PipelineErrorCode.SCHEMA_VALIDATION_FAILED,
                status="error",
                message=str(exc),
                next_action="Fix payload shape and retry.",
            )
        except Exception as exc:
            logger.exception(
                "pipeline_unhandled_error trace_id=%s error=%s",
                trace_id,
                exc,
            )
            return _error_result(
                trace_id=trace_id,
                logs=logs,
                code=PipelineErrorCode.TOOL_EXECUTION_FAILED,
                status="error",
                message=str(exc),
                next_action="Inspect logs and failing tool; retry after mitigation.",
            )

    try:
        return await asyncio.wait_for(
            _run(), timeout=policy.global_request_timeout_seconds
        )
    except asyncio.TimeoutError:
        logger.exception("pipeline_timeout trace_id=%s", trace_id)
        return _error_result(
            trace_id=trace_id,
            logs=logs,
            code=PipelineErrorCode.RETRIEVAL_TIMEOUT,
            status="error",
            message="Pipeline timed out.",
            next_action="Retry with narrowed scope or smaller query.",
        )


def _minimum_evidence_threshold(
    *,
    incident: dict | None,
    evidence: list[dict],
    services: list[dict],
    docs: list[dict],
    historical_incidents: list[dict],
    resolutions: list[dict],
) -> bool:
    incident_path = incident is not None and bool(evidence)
    service_docs_path = bool(
        [s for s in services if s.get("depends_on_service_name")]
    ) and bool(docs)
    docs_only_path = bool(docs)
    ownership_path = bool(
        [
            s
            for s in services
            if s.get("owner_name")
            or s.get("owner_email")
            or s.get("contact_value")
            or s.get("contact_type")
        ]
    )
    historical_path = bool(historical_incidents) and bool(resolutions)
    return (
        incident_path
        or service_docs_path
        or docs_only_path
        or ownership_path
        or historical_path
    )


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


def _elapsed_ms(start: float) -> int:
    return int((perf_counter() - start) * 1000)
