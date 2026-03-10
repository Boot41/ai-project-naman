from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.agent import run_agent
from app.api.deps import db_session
from app.auth.deps import current_user
from app.db.models import User
from app.services.chat import (
    create_chat_turn,
    create_session,
    delete_session_for_user,
    get_messages_for_session,
    list_sessions_with_counts,
)

router = APIRouter(prefix="/chat", tags=["chat"])


class SessionCreateRequest(BaseModel):
    incident_id: int | None = None
    title: str | None = None


class SessionOut(BaseModel):
    id: UUID
    user_id: int
    incident_id: int | None
    session_type: str
    title: str | None
    status: str
    created_at: datetime
    last_activity_at: datetime
    message_count: int = 0

    model_config = {"from_attributes": True}


class SessionListResponse(BaseModel):
    sessions: list[SessionOut]


class MessageCreateRequest(BaseModel):
    content_text: str = Field(min_length=1)
    structured_json: dict[str, object] | None = None


class MessageOut(BaseModel):
    id: UUID
    session_id: UUID
    role: str
    content_text: str
    structured_json: dict[str, object] | None
    created_at: datetime

    model_config = {"from_attributes": True}


class MessageListResponse(BaseModel):
    messages: list[MessageOut]


class MessageCreateResponse(BaseModel):
    user_message: MessageOut
    assistant_message: MessageOut


@router.get("/sessions", response_model=SessionListResponse)
async def get_sessions(
    search: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(db_session),
    user: User = Depends(current_user),
) -> SessionListResponse:
    sessions_with_counts = await list_sessions_with_counts(
        db, user_id=user.id, search=search, limit=limit, offset=offset
    )
    return SessionListResponse(
        sessions=[
            SessionOut.model_validate(session).model_copy(update={"message_count": count})
            for session, count in sessions_with_counts
        ]
    )


@router.post("/sessions", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
async def post_session(
    body: SessionCreateRequest,
    db: AsyncSession = Depends(db_session),
    user: User = Depends(current_user),
) -> SessionOut:
    session = await create_session(
        db,
        user_id=user.id,
        incident_id=body.incident_id,
        title=body.title,
    )
    return SessionOut.model_validate(session)


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: UUID,
    db: AsyncSession = Depends(db_session),
    user: User = Depends(current_user),
) -> None:
    deleted = await delete_session_for_user(db, session_id=session_id, user_id=user.id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")


@router.get("/sessions/{session_id}/messages", response_model=MessageListResponse)
async def get_messages(
    session_id: UUID,
    db: AsyncSession = Depends(db_session),
    user: User = Depends(current_user),
) -> MessageListResponse:
    session, messages = await get_messages_for_session(db, session_id=session_id, user_id=user.id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return MessageListResponse(messages=[MessageOut.model_validate(m) for m in messages])


@router.post(
    "/sessions/{session_id}/messages",
    response_model=MessageCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_message(
    session_id: UUID,
    body: MessageCreateRequest,
    db: AsyncSession = Depends(db_session),
    user: User = Depends(current_user),
) -> MessageCreateResponse:
    user_message, assistant_message = await create_chat_turn(
        db,
        session_id=session_id,
        user_id=user.id,
        content_text=body.content_text,
        structured_json=body.structured_json,
        assistant_runner=run_agent,
    )
    if user_message is None or assistant_message is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return MessageCreateResponse(
        user_message=MessageOut.model_validate(user_message),
        assistant_message=MessageOut.model_validate(assistant_message),
    )
