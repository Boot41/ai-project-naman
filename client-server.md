# Client-Server Integration Spec (OpsCopilot)

## 1. Overview
This document defines the runtime contract between `client/` and `server/` for authentication and chat CRUD.

Goals:
- Replace frontend mock auth/chat state with DB-backed APIs.
- Persist sessions and messages in PostgreSQL.
- Support chat CRUD (`create`, `read`, `delete`) and message send flow.

## 2. Authentication Contract

### Login
- Endpoint: `POST /auth/login`
- Request:
```json
{ "username": "user@example.com", "password": "secret" }
```
- Response:
```json
{
  "access_token": "...",
  "refresh_token": "...",
  "token_type": "bearer",
  "expires_in": 900,
  "user": {
    "id": 1,
    "username": "ops_user",
    "email": "user@example.com",
    "full_name": "Ops User",
    "role": "operations_engineer"
  }
}
```

### Refresh
- Endpoint: `POST /auth/refresh`
- Request: `{ "refresh_token": "..." }`
- Response: same shape as login (new tokens)

### Logout
- Endpoint: `POST /auth/logout`
- Request: `{ "refresh_token": "..." }`
- Response: `{ "success": true }`

### Frontend Token Rules
- Store auth payload in localStorage key: `opscopilot.auth`.
- Send `Authorization: Bearer <access_token>` for protected APIs.
- On `401` (non-auth endpoint), attempt one refresh and retry once.
- If refresh fails, clear storage and force signed-out state.

## 3. Chat CRUD Contract
All endpoints below are protected under `/api/v1`.

### List Sessions
- `GET /api/v1/chat/sessions?search=&limit=&offset=`
- Response:
```json
{
  "sessions": [
    {
      "id": "uuid",
      "user_id": 1,
      "incident_id": null,
      "session_type": "chat",
      "title": "Database latency",
      "status": "active",
      "created_at": "...",
      "last_activity_at": "...",
      "message_count": 2
    }
  ]
}
```

### Create Session
- `POST /api/v1/chat/sessions`
- Request:
```json
{ "incident_id": null, "title": null }
```
- Response: one session object.

Notes:
- Session type is fixed to `chat` in MVP (no investigation mode switch).

### Delete Session (Hard Delete)
- `DELETE /api/v1/chat/sessions/{session_id}`
- Behavior: permanently deletes session and all its messages.
- Response: `204 No Content`.

### List Messages
- `GET /api/v1/chat/sessions/{session_id}/messages`
- Response:
```json
{
  "messages": [
    {
      "id": "uuid",
      "session_id": "uuid",
      "role": "user",
      "content_text": "What is the issue?",
      "structured_json": null,
      "created_at": "..."
    }
  ]
}
```

### Send Message
- `POST /api/v1/chat/sessions/{session_id}/messages`
- Request:
```json
{ "content_text": "Investigate checkout latency", "structured_json": null }
```
- Response:
```json
{
  "user_message": { "id": "...", "role": "user", "content_text": "...", "session_id": "...", "structured_json": null, "created_at": "..." },
  "assistant_message": { "id": "...", "role": "assistant", "content_text": "...", "session_id": "...", "structured_json": { "summary": "..." }, "created_at": "..." }
}
```

## 4. Session Naming Logic
Applied when first user message is created and current title is empty or `"New Investigation"`:
1. Trim leading/trailing whitespace.
2. Collapse repeated whitespace to single spaces.
3. Use first 48 characters.
4. If empty after normalization, fallback to `"New Investigation"`.

## 5. Frontend State Mapping
- `ChatSession.title` <- `session.title ?? "New Investigation"`
- `ChatSession.lastActivityAt` <- `session.last_activity_at`
- `ChatMessage.content` <- `message.content_text`
- `ChatMessage.structuredJson` <- `message.structured_json`

UI behavior:
- On app load: fetch sessions, select first session if present.
- On session select: fetch messages.
- On send: append returned `user_message` and `assistant_message`.
- On delete active session: select next available session or show empty state.

## 6. Error Handling
- `401`: invalid/expired access token; frontend tries refresh once.
- `404`: session not found or not owned by user.
- `422`: validation errors (empty content, malformed payload).

## 7. Security + Access
- Single application role: `operations_engineer`.
- Only authenticated active users can access `/api/v1/chat/*`.
- Session CRUD is user-scoped (owners only).
