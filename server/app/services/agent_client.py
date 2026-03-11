from __future__ import annotations

import logging
from http import HTTPStatus
from uuid import UUID, uuid4

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class AgentClientError(Exception):
    """Raised when the external ops-agent service cannot fulfill a request."""


async def investigate_ops_agent(
    *,
    query: str,
    user_id: int,
    session_id: UUID,
    incident_key: str | None = None,
    service_name: str | None = None,
) -> tuple[str, dict[str, object]]:
    settings = get_settings()
    url = f"{settings.ops_agent_base_url.rstrip('/')}/v1/investigate"
    request_id = str(uuid4())
    payload = {
        "request_id": request_id,
        "session_id": str(session_id),
        "user_id": user_id,
        "query": query,
        "incident_key": incident_key,
        "service_name": service_name,
    }
    logger.info(
        "ops_agent_request_start request_id=%s session_id=%s user_id=%s url=%s",
        request_id,
        session_id,
        user_id,
        url,
    )

    try:
        async with httpx.AsyncClient(timeout=settings.ops_agent_timeout_seconds) as client:
            response = await client.post(url, json=payload)
    except httpx.HTTPError as exc:
        logger.exception(
            "ops_agent_request_http_error request_id=%s session_id=%s error=%r",
            request_id,
            session_id,
            exc,
        )
        raise AgentClientError(f"Agent service request failed: {exc}") from exc

    logger.info(
        "ops_agent_request_done request_id=%s session_id=%s status_code=%s",
        request_id,
        session_id,
        response.status_code,
    )
    if response.status_code != HTTPStatus.OK:
        logger.error(
            "ops_agent_request_bad_status request_id=%s session_id=%s status_code=%s body=%s",
            request_id,
            session_id,
            response.status_code,
            response.text[:400],
        )
        raise AgentClientError(
            f"Agent service returned {response.status_code}: {response.text[:200]}"
        )

    try:
        data = response.json()
    except ValueError as exc:
        logger.exception(
            "ops_agent_request_non_json request_id=%s session_id=%s",
            request_id,
            session_id,
        )
        raise AgentClientError("Agent service returned a non-JSON response body.") from exc

    output = data.get("output")
    error = data.get("error")

    if isinstance(output, dict):
        summary = output.get("summary")
        if isinstance(summary, str) and summary.strip():
            logger.info(
                "ops_agent_response_ok request_id=%s session_id=%s status=%s",
                request_id,
                session_id,
                data.get("status"),
            )
            return summary, output

    if isinstance(error, dict):
        message = error.get("message")
        next_action = error.get("next_action")
        detail = " ".join(
            part for part in [str(message or "").strip(), str(next_action or "").strip()] if part
        ).strip()
        if detail:
            logger.warning(
                "ops_agent_response_error_payload request_id=%s session_id=%s status=%s detail=%s",
                request_id,
                session_id,
                data.get("status"),
                detail,
            )
            return detail, {"status": data.get("status"), "error": error}

    logger.error(
        "ops_agent_response_invalid_payload request_id=%s session_id=%s payload=%s",
        request_id,
        session_id,
        str(data)[:800],
    )
    raise AgentClientError("Agent service response missing valid 'output' or 'error' fields.")


async def query_ops_agent(*, query: str, user_id: str) -> str:
    summary, _structured = await investigate_ops_agent(
        query=query,
        user_id=int(user_id),
        session_id=uuid4(),
    )
    return summary
