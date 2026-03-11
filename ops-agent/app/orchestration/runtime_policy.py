from __future__ import annotations

from dataclasses import dataclass

from app.contracts.incident_analysis import LoopRuntimePolicy


@dataclass(frozen=True)
class PipelineRuntimePolicy:
    global_request_timeout_seconds: int = 90
    analysis: LoopRuntimePolicy = LoopRuntimePolicy()
