from __future__ import annotations

from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.contracts.context_builder import ContextContent
from app.contracts.incident_analysis import AnalysisHypothesis
from app.contracts.orchestrator import InvestigationScope


class OutputStatus(str, Enum):
    COMPLETE = "complete"
    INCONCLUSIVE = "inconclusive"
    NOT_FOUND = "not_found"
    ERROR = "error"


class EvidenceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ref: str = Field(min_length=1)
    source: Literal["db", "docs", "session"]
    snippet: str = Field(min_length=1)


class SimilarIncidentItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    incident_key: str = Field(min_length=1)
    similarity_reason: str = Field(min_length=1)


class OwnerItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service_name: str = Field(min_length=1)
    owner: str | None = None


class EscalationItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service_name: str = Field(min_length=1)
    contacts: list[str] = Field(default_factory=list)


class ComposerInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1)
    session_id: UUID
    query: str = Field(min_length=1)
    investigation_scope: InvestigationScope
    context_content: ContextContent
    hypotheses: list[AnalysisHypothesis] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    status: OutputStatus


class ComposerOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1)
    hypotheses: list[AnalysisHypothesis] = Field(default_factory=list)
    similar_incidents: list[SimilarIncidentItem] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    owners: list[OwnerItem] = Field(default_factory=list)
    escalation: list[EscalationItem] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    report: str = Field(min_length=1)
    status: OutputStatus

    @field_validator("recommended_actions")
    @classmethod
    def validate_actions_not_empty_strings(cls, value: list[str]) -> list[str]:
        for action in value:
            if not action.strip():
                raise ValueError("recommended_actions cannot include empty strings")
        return value
