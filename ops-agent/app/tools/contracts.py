from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

_INCIDENT_PATTERN = re.compile(r"^INC-(?:\d{4}-\d{4}|\d+)$")


class ToolError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1)
    message: str = Field(min_length=1)


class ToolResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    data: Any
    error: ToolError | None = None
    source: str = Field(min_length=1)


def make_success_response(source: str, data: Any) -> ToolResponse:
    return ToolResponse(ok=True, data=data, error=None, source=source)


def make_no_data_response(source: str, *, object_mode: bool = False) -> ToolResponse:
    empty = {} if object_mode else []
    return ToolResponse(ok=True, data=empty, error=None, source=source)


def make_error_response(source: str, code: str, message: str) -> ToolResponse:
    return ToolResponse(
        ok=False, data=[], error=ToolError(code=code, message=message), source=source
    )


def validate_incident_key(incident_key: str | None) -> None:
    if incident_key is None:
        return
    if not _INCIDENT_PATTERN.match(incident_key):
        raise ValueError(
            "incident_key must match legacy INC-123 or canonical INC-2026-0001"
        )


def validate_confidence(confidence: float) -> None:
    if confidence < 0.0 or confidence > 1.0:
        raise ValueError("confidence must be within [0.0, 1.0]")


def validate_iso8601_utc(timestamp: str) -> None:
    try:
        datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("timestamp must be ISO-8601") from exc


def build_tool_log(
    *,
    trace_id: str,
    tool: str,
    args: dict[str, Any],
    response: ToolResponse,
    latency_ms: int,
) -> dict[str, Any]:
    payload = json.dumps(args, sort_keys=True, separators=(",", ":"))
    args_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()

    result_count = 0
    if isinstance(response.data, list):
        result_count = len(response.data)
    elif isinstance(response.data, dict):
        result_count = len(response.data)

    return {
        "trace_id": trace_id,
        "tool": tool,
        "args_hash": args_hash,
        "ok": response.ok,
        "result_count": result_count,
        "latency_ms": latency_ms,
        "error_code": response.error.code if response.error else None,
    }
