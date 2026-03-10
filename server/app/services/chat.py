from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import Message, Session

DEFAULT_SESSION_TITLE = "New Investigation"
ASSISTANT_FALLBACK_REPLY = (
    "I have logged your message and started the investigation context. "
    "Please continue with incident details."
)


def _now_utc() -> datetime:
    # Database columns use TIMESTAMP WITHOUT TIME ZONE, so persist naive UTC.
    return datetime.now(UTC).replace(tzinfo=None)


def build_session_title_from_first_message(content_text: str) -> str:
    normalized = " ".join(content_text.strip().split())
    if not normalized:
        return DEFAULT_SESSION_TITLE
    return normalized[:48]


async def list_sessions(
    db: AsyncSession, *, user_id: int, search: str | None = None, limit: int = 50, offset: int = 0
) -> list[Session]:
    query = select(Session).where(Session.user_id == user_id)
    if search and search.strip():
        query = query.where(Session.title.ilike(f"%{search.strip()}%"))
    query = query.order_by(Session.last_activity_at.desc()).limit(limit).offset(offset)
    result = await db.execute(query)
    return list(result.scalars().all())


async def list_sessions_with_counts(
    db: AsyncSession, *, user_id: int, search: str | None = None, limit: int = 50, offset: int = 0
) -> list[tuple[Session, int]]:
    sessions = await list_sessions(db, user_id=user_id, search=search, limit=limit, offset=offset)
    counts = await count_messages_for_sessions(db, session_ids=[s.id for s in sessions])
    return [(session, counts.get(session.id, 0)) for session in sessions]


async def create_session(
    db: AsyncSession,
    *,
    user_id: int,
    incident_id: int | None = None,
    title: str | None = None,
) -> Session:
    session = Session(
        user_id=user_id,
        incident_id=incident_id,
        session_type="chat",
        title=title or DEFAULT_SESSION_TITLE,
        status="active",
        last_activity_at=_now_utc(),
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


async def get_session_for_user(
    db: AsyncSession, *, session_id: UUID, user_id: int
) -> Session | None:
    result = await db.execute(
        select(Session).where(Session.id == session_id, Session.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def get_messages_for_session(
    db: AsyncSession, *, session_id: UUID, user_id: int
) -> tuple[Session | None, list[Message]]:
    session = await get_session_for_user(db, session_id=session_id, user_id=user_id)
    if session is None:
        return None, []
    result = await db.execute(
        select(Message).where(Message.session_id == session_id).order_by(Message.created_at.asc())
    )
    return session, list(result.scalars().all())


async def add_user_message(
    db: AsyncSession,
    *,
    session: Session,
    content_text: str,
    structured_json: dict[str, object] | None = None,
) -> Message:
    message = Message(
        session_id=session.id,
        role="user",
        content_text=content_text,
        structured_json=structured_json,
    )
    db.add(message)

    if session.title is None or session.title.strip() in {"", DEFAULT_SESSION_TITLE}:
        session.title = build_session_title_from_first_message(content_text)
    session.last_activity_at = _now_utc()

    await db.commit()
    await db.refresh(message)
    return message


async def add_assistant_message(
    db: AsyncSession,
    *,
    session: Session,
    content_text: str,
    structured_json: dict[str, object] | None = None,
) -> Message:
    message = Message(
        session_id=session.id,
        role="assistant",
        content_text=content_text,
        structured_json=structured_json,
    )
    db.add(message)
    session.last_activity_at = _now_utc()
    await db.commit()
    await db.refresh(message)
    return message


def build_assistant_structured_payload(reply_text: str) -> dict[str, object]:
    return {
        "summary": reply_text,
        "hypotheses": [],
        "similar_incidents": [],
        "evidence": [],
        "owners": [],
        "escalation": [],
        "recommended_actions": [],
        "report": None,
    }


async def create_chat_turn(
    db: AsyncSession,
    *,
    session_id: UUID,
    user_id: int,
    content_text: str,
    structured_json: dict[str, object] | None,
    assistant_runner: Callable[[str, str], Awaitable[str]],
) -> tuple[Message | None, Message | None]:
    session = await get_session_for_user(db, session_id=session_id, user_id=user_id)
    if session is None:
        return None, None

    user_message = await add_user_message(
        db, session=session, content_text=content_text, structured_json=structured_json
    )

    settings = get_settings()
    if not settings.google_api_key:
        reply_text = ASSISTANT_FALLBACK_REPLY
    else:
        try:
            reply_text = await assistant_runner(content_text, str(user_id))
        except Exception:
            reply_text = ASSISTANT_FALLBACK_REPLY

    assistant_structured = build_assistant_structured_payload(reply_text)
    assistant_message = await add_assistant_message(
        db,
        session=session,
        content_text=reply_text,
        structured_json=assistant_structured,
    )
    return user_message, assistant_message


async def delete_session_for_user(db: AsyncSession, *, session_id: UUID, user_id: int) -> bool:
    session = await get_session_for_user(db, session_id=session_id, user_id=user_id)
    if session is None:
        return False
    await db.execute(delete(Message).where(Message.session_id == session_id))
    await db.execute(delete(Session).where(Session.id == session_id))
    await db.commit()
    return True


async def count_messages_for_sessions(
    db: AsyncSession, *, session_ids: list[UUID]
) -> dict[UUID, int]:
    if not session_ids:
        return {}
    result = await db.execute(
        select(Message.session_id, func.count(Message.id))
        .where(Message.session_id.in_(session_ids))
        .group_by(Message.session_id)
    )
    return {session_id: count for session_id, count in result.all()}
