from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

import app.db.models  # noqa: F401 — register all models
from app.api.router import root_router
from app.auth.passwords import hash_password
from app.core import config as config_module
from app.core.config import get_settings
from app.db.base import Base
from app.db.models import User
from app.middleware.error_handler import ErrorHandlerMiddleware
from app.middleware.request_logging import RequestLoggingMiddleware

TEST_SECRET_KEY = "test-only-secret-key-at-least-32-bytes-long"


def _create_test_app() -> FastAPI:
    """Create a FastAPI app without lifespan (no shared engine)."""
    test_app = FastAPI(title="Test")
    test_app.add_middleware(RequestLoggingMiddleware)
    test_app.add_middleware(ErrorHandlerMiddleware)
    test_app.include_router(root_router)
    return test_app


@pytest.fixture(autouse=True)
def fixed_test_secret(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SECRET_KEY", TEST_SECRET_KEY)
    config_module.get_settings.cache_clear()
    yield
    config_module.get_settings.cache_clear()


@pytest.fixture
async def engine():  # type: ignore[no-untyped-def]
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


@pytest.fixture
async def session_factory(engine):  # type: ignore[no-untyped-def]
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
async def db(session_factory):  # type: ignore[no-untyped-def]
    async with session_factory() as session:
        yield session


@pytest.fixture
async def client(session_factory):  # type: ignore[no-untyped-def]
    from app.api.deps import db_session as db_session_dep

    test_app = _create_test_app()

    async def _override() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            yield session

    test_app.dependency_overrides[db_session_dep] = _override
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def seed_user(db: AsyncSession) -> User:
    user = User(
        username="testuser",
        email="test@example.com",
        full_name="Test User",
        role="operations_engineer",
        password_hash=hash_password("testpass"),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


def make_token(user_id: int) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "type": "access",
        "role": "operations_engineer",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=1)).timestamp()),
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


@pytest.fixture
def auth_headers(seed_user: User) -> dict[str, str]:
    token = make_token(seed_user.id)
    return {"Authorization": f"Bearer {token}"}
