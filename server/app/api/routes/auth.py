from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session
from app.services.auth import ACCESS_TOKEN_TTL_SECONDS, login, logout, refresh_tokens

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: int
    username: str
    email: str
    full_name: str | None
    role: str

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = ACCESS_TOKEN_TTL_SECONDS
    user: UserOut


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class LogoutResponse(BaseModel):
    success: bool


@router.post("/login", response_model=TokenResponse)
async def do_login(body: LoginRequest, db: AsyncSession = Depends(db_session)) -> TokenResponse:
    access_token, refresh_token, user = await login(db, body.username, body.password)
    if not access_token or not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserOut.model_validate(user),
    )


@router.post("/refresh", response_model=TokenResponse)
async def do_refresh(body: RefreshRequest, db: AsyncSession = Depends(db_session)) -> TokenResponse:
    access_token, refresh_token, user = await refresh_tokens(db, body.refresh_token)
    if not access_token or not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        )
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserOut.model_validate(user),
    )


@router.post("/logout", response_model=LogoutResponse)
async def do_logout(body: LogoutRequest, db: AsyncSession = Depends(db_session)) -> LogoutResponse:
    revoked = await logout(db, body.refresh_token)
    if not revoked:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        )
    return LogoutResponse(success=True)
