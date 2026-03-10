from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from httpx import ASGITransport, AsyncClient

from app.core import config as config_module
from app.core.config import get_settings
from app.main import app

TEST_SECRET_KEY = "test-only-secret-key-at-least-32-bytes-long"


@pytest.fixture(autouse=True)
def fixed_test_secret(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SECRET_KEY", TEST_SECRET_KEY)
    config_module.get_settings.cache_clear()
    yield
    config_module.get_settings.cache_clear()


@pytest.fixture
def auth_token() -> str:
    """Generate a valid JWT token for user_id=1."""
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": "1",
        "type": "access",
        "role": "operations_engineer",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=1)).timestamp()),
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client mounted on the FastAPI test app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
