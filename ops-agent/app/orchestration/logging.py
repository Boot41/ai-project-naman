from __future__ import annotations

from typing import Any


def build_step_log(
    *,
    trace_id: str,
    request_id: str,
    session_id: str,
    user_id: int,
    agent: str,
    step: str,
    status: str,
    latency_ms: int,
    confidence: float = 0.0,
    evidence_refs: list[str] | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> dict[str, Any]:
    return {
        "trace_id": trace_id,
        "request_id": request_id,
        "session_id": session_id,
        "user_id": user_id,
        "agent": agent,
        "step": step,
        "status": status,
        "latency_ms": latency_ms,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "confidence": confidence,
        "evidence_refs": evidence_refs or [],
    }
