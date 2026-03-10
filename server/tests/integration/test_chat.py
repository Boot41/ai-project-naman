from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.passwords import hash_password
from app.db.models import User


@pytest.mark.asyncio
async def test_chat_session_crud_flow(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    create_resp = await client.post("/api/v1/chat/sessions", headers=auth_headers, json={})
    assert create_resp.status_code == 201
    session = create_resp.json()
    session_id = session["id"]
    assert session["title"] == "New Investigation"

    list_resp = await client.get("/api/v1/chat/sessions", headers=auth_headers)
    assert list_resp.status_code == 200
    sessions = list_resp.json()["sessions"]
    assert any(s["id"] == session_id for s in sessions)

    delete_resp = await client.delete(f"/api/v1/chat/sessions/{session_id}", headers=auth_headers)
    assert delete_resp.status_code == 204

    messages_resp = await client.get(
        f"/api/v1/chat/sessions/{session_id}/messages", headers=auth_headers
    )
    assert messages_resp.status_code == 404


@pytest.mark.asyncio
async def test_post_message_sets_title_and_persists_two_messages(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    create_resp = await client.post("/api/v1/chat/sessions", headers=auth_headers, json={})
    session_id = create_resp.json()["id"]

    send_resp = await client.post(
        f"/api/v1/chat/sessions/{session_id}/messages",
        headers=auth_headers,
        json={"content_text": "Database latency on checkout service from us-east-1"},
    )
    assert send_resp.status_code == 201
    payload = send_resp.json()
    assert payload["user_message"]["role"] == "user"
    assert payload["assistant_message"]["role"] == "assistant"

    list_sessions = await client.get("/api/v1/chat/sessions", headers=auth_headers)
    sessions = list_sessions.json()["sessions"]
    current = next(s for s in sessions if s["id"] == session_id)
    assert current["title"] != "New Investigation"
    assert current["title"].startswith("Database latency on checkout service")
    assert len(current["title"]) <= 48

    messages_resp = await client.get(
        f"/api/v1/chat/sessions/{session_id}/messages", headers=auth_headers
    )
    assert messages_resp.status_code == 200
    messages = messages_resp.json()["messages"]
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"


@pytest.mark.asyncio
async def test_chat_routes_require_auth(client: AsyncClient) -> None:
    response = await client.get("/api/v1/chat/sessions")
    assert response.status_code in {401, 403}


@pytest.mark.asyncio
async def test_chat_session_access_is_user_scoped(
    client: AsyncClient, auth_headers: dict[str, str], db: AsyncSession
) -> None:
    create_resp = await client.post("/api/v1/chat/sessions", headers=auth_headers, json={})
    assert create_resp.status_code == 201
    session_id = create_resp.json()["id"]

    other_user = User(
        username="otheruser",
        email="other@example.com",
        full_name="Other User",
        role="operations_engineer",
        password_hash=hash_password("otherpass"),
    )
    db.add(other_user)
    await db.commit()
    await db.refresh(other_user)

    login_other = await client.post(
        "/auth/login", json={"username": "other@example.com", "password": "otherpass"}
    )
    assert login_other.status_code == 200
    other_access = login_other.json()["access_token"]
    other_headers = {"Authorization": f"Bearer {other_access}"}

    read_resp = await client.get(
        f"/api/v1/chat/sessions/{session_id}/messages", headers=other_headers
    )
    assert read_resp.status_code == 404

    del_resp = await client.delete(f"/api/v1/chat/sessions/{session_id}", headers=other_headers)
    assert del_resp.status_code == 404
