from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.contracts.context_builder import ContextContent
from app.contracts.orchestrator import InvestigationScope


class AnalysisDecision(str, Enum):
    CONTINUE = "continue"
    STOP = "stop"
    INCONCLUSIVE = "inconclusive"


class AnalysisHypothesis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cause: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    supporting_evidence_refs: list[str] = Field(min_length=1)
    counter_evidence_refs: list[str] = Field(default_factory=list)
    reasoning_summary: str = Field(min_length=1)


class IterationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    iteration: int
    requested_additional_tools: list[str] = Field(default_factory=list)
    received_evidence_count: int
    confidence_delta: float
    decision: AnalysisDecision


class IncidentAnalysisInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1)
    session_id: UUID
    query: str = Field(min_length=1)
    investigation_scope: InvestigationScope
    context_content: ContextContent
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


class IncidentAnalysisOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hypotheses: list[AnalysisHypothesis] = Field(default_factory=list)
    analysis_decision: AnalysisDecision
    missing_information: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    status: Literal["in_progress", "complete", "inconclusive"]
    iteration_summaries: list[IterationSummary] = Field(default_factory=list)


@dataclass(frozen=True)
class LoopRuntimePolicy:
    max_iterations: int = 3
    target_confidence: float = 0.75
    per_tool_timeout_seconds: int = 8
    per_iteration_budget_seconds: int = 20
    analysis_total_budget_seconds: int = 60
    max_additional_tool_calls_per_iteration: int = 4
