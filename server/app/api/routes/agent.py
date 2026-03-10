from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.auth.deps import current_user
from app.db.models import User
from app.services.agent_client import AgentClientError, query_ops_agent

router = APIRouter(prefix="/agent", tags=["agent"])


class AgentQueryRequest(BaseModel):
    message: str = Field(min_length=1)


class AgentQueryResponse(BaseModel):
    reply: str


@router.post("/query", response_model=AgentQueryResponse)
async def query_agent(
    body: AgentQueryRequest,
    user: User = Depends(current_user),
) -> AgentQueryResponse:
    try:
        reply = await query_ops_agent(query=body.message, user_id=str(user.id))
    except AgentClientError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return AgentQueryResponse(reply=reply)
