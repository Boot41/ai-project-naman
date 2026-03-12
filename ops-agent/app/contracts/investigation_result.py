from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class PipelineErrorCode(str, Enum):
    INCIDENT_NOT_FOUND = "INCIDENT_NOT_FOUND"
    RETRIEVAL_TIMEOUT = "RETRIEVAL_TIMEOUT"
    TOOL_EXECUTION_FAILED = "TOOL_EXECUTION_FAILED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class PipelineErrorPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = Field(pattern="^(error|not_found|inconclusive)$")
    error_code: PipelineErrorCode
    message: str = Field(min_length=1)
    next_action: str = Field(min_length=1)


class InvestigationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_id: str
    status: str
    output: dict | None = None
    error: PipelineErrorPayload | None = None
    logs: list[dict] = Field(default_factory=list)
    persistence: dict | None = None
