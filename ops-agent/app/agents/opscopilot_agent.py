from __future__ import annotations

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from google.adk.agents import Agent

from app.core.config import get_settings
from app.orchestration.pipeline import run_investigation_pipeline

OPSCOPILOT_PROMPT = """
You are the OpsCopilot ADK web entry agent.
Always call `run_opscopilot_pipeline` for investigation requests.
Collect optional fields if provided: incident_key, service_name, session_id, user_id.
Return the tool result as JSON.
""".strip()


def _run_async(coro: asyncio.Future) -> object:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(asyncio.run, coro).result()


def run_opscopilot_pipeline(
    query: str,
    incident_key: str | None = None,
    service_name: str | None = None,
    session_id: str | None = None,
    user_id: int = 1,
) -> dict:
    request_id = str(uuid4())
    effective_session_id = session_id or str(uuid4())

    result = _run_async(
        run_investigation_pipeline(
            request_id=request_id,
            session_id=effective_session_id,
            user_id=user_id,
            query=query,
            incident_key=incident_key,
            service_name=service_name,
        )
    )
    return result.model_dump()


settings = get_settings()
os.environ["GOOGLE_API_KEY"] = settings.required_google_api_key

root_agent = Agent(
    name="OpsCopilotADKWebAgent",
    model=settings.model_name,
    description="ADK web wrapper for full OpsCopilot pipeline execution.",
    instruction=OPSCOPILOT_PROMPT,
    tools=[run_opscopilot_pipeline],
)
