from __future__ import annotations

from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class InvestigationScope(str, Enum):
    INCIDENT = "incident"
    SERVICE = "service"
    OWNERSHIP = "ownership"
    COMPARISON = "comparison"
    REPORT = "report"


class RoutingTarget(str, Enum):
    CONTEXT_BUILDER = "context_builder"
    INCIDENT_ANALYSIS = "incident_analysis"
    RESPONSE_COMPOSER = "response_composer"


class ToolPriority(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class SessionMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timezone: str | None = None
    locale: str | None = None


class OrchestratorInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1)
    session_id: UUID
    user_id: int
    query: str = Field(min_length=1)
    incident_key: str | None = None
    service_name: str | None = None
    session_metadata: SessionMetadata = Field(default_factory=SessionMetadata)

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("query must be non-empty")
        return stripped


class ToolPlanItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str = Field(min_length=1)
    args: dict[str, Any] = Field(default_factory=dict)
    priority: ToolPriority
    reason: str = Field(min_length=1)


class ContextSeed(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    session_id: UUID
    user_id: int
    query: str
    incident_key: str | None
    service_name: str | None
    status: str = "in_progress"


class OrchestratorOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    investigation_scope: InvestigationScope
    routing_target: RoutingTarget
    tool_plan: list[ToolPlanItem]
    context_seed: ContextSeed
