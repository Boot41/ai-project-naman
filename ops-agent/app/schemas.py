from __future__ import annotations

from pydantic import BaseModel, Field


class AgentQueryRequest(BaseModel):
    query: str = Field(min_length=1)
    user_id: str = "backend-user"


class AgentQueryResponse(BaseModel):
    answer: str
