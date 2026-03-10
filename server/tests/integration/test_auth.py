from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.db.models import User


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, seed_user: User) -> None:
    response = await client.post(
        "/auth/login", json={"username": "testuser", "password": "testpass"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["user"]["username"] == "testuser"
    assert data["user"]["role"] == "operations_engineer"


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient, seed_user: User) -> None:
    response = await client.post("/auth/login", json={"username": "testuser", "password": "wrong"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_unknown_user(client: AsyncClient) -> None:
    response = await client.post("/auth/login", json={"username": "nobody", "password": "pass"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_success_rotates_token(client: AsyncClient, seed_user: User) -> None:
    login_response = await client.post(
        "/auth/login", json={"username": "testuser", "password": "testpass"}
    )
    old_refresh = login_response.json()["refresh_token"]

    refresh_response = await client.post("/auth/refresh", json={"refresh_token": old_refresh})
    assert refresh_response.status_code == 200
    data = refresh_response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["refresh_token"] != old_refresh

    old_token_again = await client.post("/auth/refresh", json={"refresh_token": old_refresh})
    assert old_token_again.status_code == 401


@pytest.mark.asyncio
async def test_logout_revokes_refresh_token(client: AsyncClient, seed_user: User) -> None:
    login_response = await client.post(
        "/auth/login", json={"username": "testuser", "password": "testpass"}
    )
    refresh_token = login_response.json()["refresh_token"]

    logout_response = await client.post("/auth/logout", json={"refresh_token": refresh_token})
    assert logout_response.status_code == 200
    assert logout_response.json()["success"] is True

    refresh_response = await client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert refresh_response.status_code == 401
