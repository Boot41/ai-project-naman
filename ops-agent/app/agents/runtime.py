from __future__ import annotations

import asyncio
import json
import os
from typing import Any, TypeVar

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from pydantic import BaseModel

from app.core.config import get_settings

T = TypeVar("T", bound=BaseModel)


def ensure_adk_key_configured() -> None:
    settings = get_settings()
    if not settings.google_api_key.strip():
        raise RuntimeError(
            "GOOGLE_API_KEY is not configured in ops-agent/.env or environment."
        )


def build_stage_agent(
    *, name: str, instruction: str, tools: list[Any] | None = None
) -> Agent:
    settings = get_settings()
    key = settings.google_api_key.strip()
    if key:
        os.environ["GOOGLE_API_KEY"] = key

    return Agent(
        name=name,
        model=settings.model_name,
        description=f"{name} for OpsCopilot pipeline",
        instruction=instruction,
        tools=tools or [],
    )


async def run_json_stage(
    *, agent: Agent, payload: BaseModel, output_model: type[T], user_id: str
) -> T:
    settings = get_settings()
    ensure_adk_key_configured()
    os.environ["GOOGLE_API_KEY"] = settings.google_api_key.strip()

    session_service = InMemorySessionService()  # type: ignore[no-untyped-call]
    session = await session_service.create_session(
        app_name=settings.app_name, user_id=user_id
    )
    runner = Runner(
        agent=agent, app_name=settings.app_name, session_service=session_service
    )

    prompt = (
        "Return strict JSON only.\n"
        "The response MUST validate against this JSON schema.\n"
        f"OUTPUT_SCHEMA_JSON:\n{json.dumps(output_model.model_json_schema(), ensure_ascii=True)}\n"
        f"INPUT_JSON:\n{payload.model_dump_json()}\n"
    )
    content = types.Content(role="user", parts=[types.Part.from_text(text=prompt)])

    final_text = ""
    async for event in runner.run_async(
        user_id=user_id, session_id=session.id, new_message=content
    ):
        if event.is_final_response() and event.content and event.content.parts:
            final_text = event.content.parts[0].text or ""

    parsed = _extract_json(final_text)
    return output_model.model_validate(parsed)


async def run_json_stage_with_timeout(
    *,
    agent: Agent,
    payload: BaseModel,
    output_model: type[T],
    user_id: str,
    timeout_seconds: float,
) -> T:
    return await asyncio.wait_for(
        asyncio.to_thread(
            asyncio.run,
            run_json_stage(
                agent=agent,
                payload=payload,
                output_model=output_model,
                user_id=user_id,
            ),
        ),
        timeout=timeout_seconds,
    )


def _extract_json(text: str) -> dict:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        return json.loads(text[start : end + 1])
