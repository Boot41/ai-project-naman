from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import Awaitable
from concurrent.futures import TimeoutError as FutureTimeoutError
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from app.agents.orchestrator_agent import root_agent
from app.contracts.investigation_result import (
    InvestigationResult,
    PipelineErrorCode,
    PipelineErrorPayload,
)
from app.core.config import get_settings
from app.services.enrichment import enrich_investigation_facts, enrich_owner_escalation
from app.services.output_normalizer import extract_json, normalize_composer_payload

logger = logging.getLogger(__name__)
_shared_session_service = InMemorySessionService()  # type: ignore[no-untyped-call]


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
