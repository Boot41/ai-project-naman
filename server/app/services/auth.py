from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from secrets import token_urlsafe
from uuid import uuid4

import jwt
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.passwords import verify_password
from app.core.config import get_settings
from app.db.models import User

ACCESS_TOKEN_TTL_SECONDS = 15 * 60
REFRESH_TOKEN_TTL_DAYS = 7
ALGORITHM = "HS256"


def _now_db_utc() -> datetime:
    # Database columns use TIMESTAMP WITHOUT TIME ZONE, so persist naive UTC.
    return datetime.now(UTC).replace(tzinfo=None)


def _refresh_token_hash(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def _now_jwt_utc() -> datetime:
    return datetime.now(UTC)


def _create_access_token(user: User) -> str:
    settings = get_settings()
    now = _now_jwt_utc()
    payload = {
        "sub": str(user.id),
        "type": "access",
        "role": user.role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ACCESS_TOKEN_TTL_SECONDS)).timestamp()),
        "jti": str(uuid4()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def _new_refresh_token() -> str:
    return token_urlsafe(48)


async def login(
    db: AsyncSession, username_or_email: str, password: str
) -> tuple[str | None, str | None, User | None]:
    result = await db.execute(
        select(User).where(or_(User.username == username_or_email, User.email == username_or_email))
    )
    user = result.scalar_one_or_none()

    if (
        user is None
        or not verify_password(password, user.password_hash)
        or not user.is_active
        or user.role != "operations_engineer"
    ):
        return None, None, None

    access_token = _create_access_token(user)
    refresh_plain = _new_refresh_token()
    now = _now_db_utc()
    user.refresh_token_hash = _refresh_token_hash(refresh_plain)
    user.refresh_token_issued_at = now
    user.refresh_token_expires_at = now + timedelta(days=REFRESH_TOKEN_TTL_DAYS)
    user.refresh_token_revoked_at = None
    await db.commit()
    return access_token, refresh_plain, user


async def refresh_tokens(
    db: AsyncSession, refresh_token: str
) -> tuple[str | None, str | None, User | None]:
    result = await db.execute(
        select(User).where(User.refresh_token_hash == _refresh_token_hash(refresh_token))
    )
    user = result.scalar_one_or_none()
    now = _now_db_utc()
    if user is None:
        return None, None, None

    if (
        user.refresh_token_expires_at is None
        or user.refresh_token_expires_at <= now
        or user.refresh_token_revoked_at is not None
        or not user.is_active
        or user.role != "operations_engineer"
    ):
        return None, None, None

    # Keep refresh flow simple for MVP: renew token fields on the user row.
    new_refresh_plain = _new_refresh_token()
    user.refresh_token_hash = _refresh_token_hash(new_refresh_plain)
    user.refresh_token_issued_at = now
    user.refresh_token_expires_at = now + timedelta(days=REFRESH_TOKEN_TTL_DAYS)
    user.refresh_token_revoked_at = None
    await db.commit()
    return _create_access_token(user), new_refresh_plain, user


async def logout(db: AsyncSession, refresh_token: str) -> bool:
    result = await db.execute(
        select(User).where(User.refresh_token_hash == _refresh_token_hash(refresh_token))
    )
    user = result.scalar_one_or_none()
    if user is None or user.refresh_token_revoked_at is not None:
        return False
    user.refresh_token_revoked_at = _now_db_utc()
    await db.commit()
    return True
