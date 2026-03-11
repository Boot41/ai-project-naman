from __future__ import annotations

from app.investigation_flow import InvestigationResult, run_investigation_pipeline


async def investigate(
    *,
    request_id: str,
    session_id: str,
    user_id: int,
    query: str,
    incident_key: str | None = None,
    service_name: str | None = None,
) -> InvestigationResult:
    return await run_investigation_pipeline(
        request_id=request_id,
        session_id=session_id,
        user_id=user_id,
        query=query,
        incident_key=incident_key,
        service_name=service_name,
    )
