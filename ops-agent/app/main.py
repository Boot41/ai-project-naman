from __future__ import annotations

import logging

from fastapi import FastAPI, status

from app.schemas import (
    InvestigationRequest,
    InvestigationResponse,
)
from app.service import investigate

logger = logging.getLogger(__name__)

app = FastAPI(title="Ops Agent", version="0.1.0")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/v1/investigate",
    response_model=InvestigationResponse,
    status_code=status.HTTP_200_OK,
)
async def investigate_agent(body: InvestigationRequest) -> InvestigationResponse:
    logger.info(
        "investigate_request_start request_id=%s session_id=%s user_id=%s query=%s",
        body.request_id,
        body.session_id,
        body.user_id,
        body.query[:160],
    )
    result = await investigate(
        request_id=body.request_id,
        session_id=body.session_id,
        user_id=body.user_id,
        query=body.query,
        incident_key=body.incident_key,
        service_name=body.service_name,
    )
    logger.info(
        "investigate_request_done request_id=%s trace_id=%s status=%s error_code=%s",
        body.request_id,
        result.trace_id,
        result.status,
        result.error.error_code if result.error else None,
    )
    return InvestigationResponse(**result.model_dump())
