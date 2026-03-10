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
from app.db.models import RefreshToken, User

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
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


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
    refresh_record = RefreshToken(
        id=uuid4(),
        user_id=user.id,
        token_hash=_refresh_token_hash(refresh_plain),
        issued_at=_now_db_utc(),
        expires_at=_now_db_utc() + timedelta(days=REFRESH_TOKEN_TTL_DAYS),
    )
    db.add(refresh_record)
    await db.commit()
    return access_token, refresh_plain, user


async def refresh_tokens(
    db: AsyncSession, refresh_token: str
) -> tuple[str | None, str | None, User | None]:
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == _refresh_token_hash(refresh_token))
    )
    token_row = result.scalar_one_or_none()
    now = _now_db_utc()
    if token_row is None or token_row.revoked_at is not None or token_row.expires_at <= now:
        return None, None, None

    user_result = await db.execute(select(User).where(User.id == token_row.user_id))
    user = user_result.scalar_one_or_none()
    if user is None or not user.is_active or user.role != "operations_engineer":
        return None, None, None

    new_refresh_plain = _new_refresh_token()
    new_row = RefreshToken(
        id=uuid4(),
        user_id=user.id,
        token_hash=_refresh_token_hash(new_refresh_plain),
        issued_at=now,
        expires_at=now + timedelta(days=REFRESH_TOKEN_TTL_DAYS),
    )
    db.add(new_row)
    # Flush insert first so replaced_by_token_id always points to an existing row.
    await db.flush()
    token_row.revoked_at = now
    token_row.replaced_by_token_id = new_row.id
    await db.commit()
    return _create_access_token(user), new_refresh_plain, user


async def logout(db: AsyncSession, refresh_token: str) -> bool:
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == _refresh_token_hash(refresh_token))
    )
    token_row = result.scalar_one_or_none()
    if token_row is None or token_row.revoked_at is not None:
        return False
    token_row.revoked_at = _now_db_utc()
    await db.commit()
    return True
