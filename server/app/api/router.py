from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.routes import agent, auth, chat, health
from app.auth.deps import require_user

public_router = APIRouter()
public_router.include_router(health.router)
public_router.include_router(auth.router)

api_router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_user)])
api_router.include_router(agent.router)
api_router.include_router(chat.router)

root_router = APIRouter()
root_router.include_router(public_router)
root_router.include_router(api_router)
