from __future__ import annotations

import os

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from app.core.config import get_settings
from app.tools.web_search import web_search


def build_adk_agent() -> Agent:
    settings = get_settings()
    if settings.google_api_key:
        os.environ["GOOGLE_API_KEY"] = settings.google_api_key

    return Agent(
        name="ops_copilot_web_agent",
        model=settings.model_name,
        description="OpsCopilot MVP web-search assistant.",
        instruction=(
            "You are the OpsCopilot MVP assistant. "
            "Always use the web_search tool to answer user questions with up-to-date facts. "
            "Write a concise natural-language answer and include source URLs."
        ),
        tools=[web_search],
    )


async def run_adk_agent(user_query: str, user_id: str = "backend-user") -> str:
    session_service = InMemorySessionService()  # type: ignore[no-untyped-call]
    app_name = get_settings().app_name
    session = await session_service.create_session(app_name=app_name, user_id=user_id)
    runner = Runner(agent=build_adk_agent(), app_name=app_name, session_service=session_service)

    content = types.Content(role="user", parts=[types.Part.from_text(text=user_query)])

    final_text = ""
    async for event in runner.run_async(
        user_id=user_id,
        session_id=session.id,
        new_message=content,
    ):
        if event.is_final_response() and event.content and event.content.parts:
            final_text = event.content.parts[0].text or ""

    return final_text.strip()

