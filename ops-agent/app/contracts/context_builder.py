from __future__ import annotations

from enum import Enum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.contracts.orchestrator import InvestigationScope


class PatternRelevance(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class AffectedService(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service_name: str
    tier: str | None = None
    impact_type: str | None = None


class KeyMetric(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric_name: str
    value: float | None = None
    unit: str | None = None
    event_time: str


class ImportantEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    event_type: str
    event_time: str
    event_text: str


class DocumentationFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    doc_id: str
    category: str
    source_file: str
    finding: str


class HistoricalPattern(BaseModel):
    model_config = ConfigDict(extra="forbid")

    incident_key: str
    pattern: str
    relevance: PatternRelevance


class OwnerEscalation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service_name: str
    owner: str | None = None
    escalation_contacts: list[str] = Field(default_factory=list)


class ContextContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    incident_summary: str
    affected_services: list[AffectedService] = Field(default_factory=list)
    key_metrics: list[KeyMetric] = Field(default_factory=list)
    important_events: list[ImportantEvent] = Field(default_factory=list)
    documentation_findings: list[DocumentationFinding] = Field(default_factory=list)
    historical_patterns: list[HistoricalPattern] = Field(default_factory=list)
    owners_and_escalation: list[OwnerEscalation] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)


class ContextBuilderInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1)
    session_id: UUID
    user_id: int
    query: str = Field(min_length=1)
    incident_key: str | None = None
    service_name: str | None = None
    investigation_scope: InvestigationScope
    incident: dict[str, Any] | None = None
    services: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    docs: list[dict[str, Any]] = Field(default_factory=list)
    historical_incidents: list[dict[str, Any]] = Field(default_factory=list)
    session_history: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("query must be non-empty")
        return stripped


class ContextBuilderOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    session_id: UUID
    user_id: int
    query: str
    incident_key: str | None
    service_name: str | None
    investigation_scope: InvestigationScope
    incident: dict[str, Any] | None
    services: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    docs: list[dict[str, Any]]
    historical_incidents: list[dict[str, Any]]
    session_history: list[dict[str, Any]]
    context_content: ContextContent
    status: Literal["in_progress", "not_found"]
