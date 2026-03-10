from __future__ import annotations

from typing import Any, TypedDict
from urllib.parse import quote_plus

import httpx

from app.core.config import get_settings


class WebSearchResult(TypedDict):
    title: str
    snippet: str
    url: str


class WebSearchPayload(TypedDict):
    query: str
    results: list[WebSearchResult]


def _flatten_related_topics(items: list[dict[str, Any]]) -> list[WebSearchResult]:
    flattened: list[WebSearchResult] = []
    for item in items:
        if "Text" in item and "FirstURL" in item:
            flattened.append(
                {
                    "title": str(item["Text"]).split(" - ")[0],
                    "snippet": str(item["Text"]),
                    "url": str(item["FirstURL"]),
                }
            )
            continue
        if "Topics" in item and isinstance(item["Topics"], list):
            flattened.extend(_flatten_related_topics(item["Topics"]))
    return flattened


def web_search(query: str) -> WebSearchPayload:
    """Simple web search tool using DuckDuckGo Instant Answer API."""
    settings = get_settings()
    url = (
        "https://api.duckduckgo.com/"
        f"?q={quote_plus(query)}&format=json&no_html=1&skip_disambig=1"
    )
    with httpx.Client(timeout=settings.web_search_timeout_seconds) as client:
        response = client.get(url)
        response.raise_for_status()
        payload: dict[str, Any] = response.json()

    results: list[WebSearchResult] = []
    abstract_text = payload.get("AbstractText")
    abstract_url = payload.get("AbstractURL")
    heading = payload.get("Heading")
    if abstract_text and abstract_url:
        results.append(
            {
                "title": str(heading or "Summary"),
                "snippet": str(abstract_text),
                "url": str(abstract_url),
            }
        )

    related_topics = payload.get("RelatedTopics")
    if isinstance(related_topics, list):
        results.extend(_flatten_related_topics(related_topics))

    return {"query": query, "results": results[:5]}


def format_web_search_answer(payload: WebSearchPayload) -> str:
    """Render a natural-language fallback answer from tool results."""
    query = payload["query"]
    results = payload["results"]
    if not results:
        return (
            f"I could not find reliable web results for '{query}'. "
            "Try a more specific question with product, region, or timeframe."
        )

    first = results[0]
    lines = [
        f"Here is what I found for '{query}':",
        first["snippet"],
        f"Source: {first['url']}",
    ]

    if len(results) > 1:
        lines.append("More sources:")
        for item in results[1:3]:
            lines.append(f"- {item['title']}: {item['url']}")

    return "\n".join(lines)

