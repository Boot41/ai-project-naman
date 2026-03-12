from __future__ import annotations

from app.agents.orchestrator_runtime import run_investigation_via_root_agent
from app.contracts.investigation_result import InvestigationResult


async def run_investigation_entrypoint(
    *,
    request_id: str,
    session_id: str,
    user_id: int,
    query: str,
    incident_key: str | None = None,
    service_name: str | None = None,
) -> InvestigationResult:
    """
    Shared service/API entrypoint.
    """
    return await run_investigation_via_root_agent(
        request_id=request_id,
        session_id=session_id,
        user_id=user_id,
        query=query,
        incident_key=incident_key,
        service_name=service_name,
    )
