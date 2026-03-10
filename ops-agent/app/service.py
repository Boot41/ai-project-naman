from __future__ import annotations

from app.adk_agent import run_adk_agent
from app.tools.web_search import format_web_search_answer, web_search


async def answer_query(user_query: str, user_id: str = "backend-user") -> str:
    # Primary path: ADK agent with web_search tool.
    try:
        adk_answer = await run_adk_agent(user_query=user_query, user_id=user_id)
        if adk_answer:
            return adk_answer
    except Exception:
        pass

    # Fallback path: direct web search result rendering.
    try:
        payload = web_search(user_query)
        return format_web_search_answer(payload)
    except Exception:
        return (
            "I could not complete web search right now. "
            "Please retry in a moment."
        )

