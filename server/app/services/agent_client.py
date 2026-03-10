from __future__ import annotations

from http import HTTPStatus

import httpx

from app.core.config import get_settings


class AgentClientError(Exception):
    """Raised when the external ops-agent service cannot fulfill a request."""


async def query_ops_agent(*, query: str, user_id: str) -> str:
    settings = get_settings()
    url = f"{settings.ops_agent_base_url.rstrip('/')}/v1/query"
    payload = {"query": query, "user_id": user_id}

    try:
        async with httpx.AsyncClient(timeout=settings.ops_agent_timeout_seconds) as client:
            response = await client.post(url, json=payload)
    except httpx.HTTPError as exc:
        raise AgentClientError(f"Agent service request failed: {exc}") from exc

    if response.status_code != HTTPStatus.OK:
        raise AgentClientError(
            f"Agent service returned {response.status_code}: {response.text[:200]}"
        )

    try:
        data = response.json()
    except ValueError as exc:
        raise AgentClientError("Agent service returned a non-JSON response body.") from exc

    answer = data.get("answer")
    if not isinstance(answer, str) or not answer.strip():
        raise AgentClientError("Agent service response missing non-empty 'answer'.")
    return answer
