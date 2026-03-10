from __future__ import annotations

from fastapi import FastAPI, status

from app.schemas import AgentQueryRequest, AgentQueryResponse
from app.service import answer_query

app = FastAPI(title="Ops Agent", version="0.1.0")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/query", response_model=AgentQueryResponse, status_code=status.HTTP_200_OK)
async def query_agent(body: AgentQueryRequest) -> AgentQueryResponse:
    answer = await answer_query(body.query, body.user_id)
    return AgentQueryResponse(answer=answer)
