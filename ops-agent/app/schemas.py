from __future__ import annotations

from pydantic import BaseModel, Field


class InvestigationRequest(BaseModel):
    request_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    user_id: int
    query: str = Field(min_length=1)
    incident_key: str | None = None
    service_name: str | None = None


class InvestigationResponse(BaseModel):
    trace_id: str
    status: str
    output: dict | None = None
    error: dict | None = None
    logs: list[dict] = Field(default_factory=list)
    persistence: dict | None = None
