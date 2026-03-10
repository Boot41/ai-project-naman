from __future__ import annotations

from app.services.chat import DEFAULT_SESSION_TITLE, build_session_title_from_first_message


def test_build_session_title_from_first_message_trims_and_limits() -> None:
    raw = "   Database    latency   in   checkout service   for us-east-1 region   "
    title = build_session_title_from_first_message(raw)
    assert title == "Database latency in checkout service for us-east"
    assert len(title) == 48


def test_build_session_title_from_first_message_fallback() -> None:
    title = build_session_title_from_first_message("   \n\t   ")
    assert title == DEFAULT_SESSION_TITLE
