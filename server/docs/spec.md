# OpsCopilot Backend Architecture & Schema Spec

## 1. Summary
OpsCopilot is a backend system for incident investigation that combines:
- Structured operational data from PostgreSQL.
- Local documentation files (runbooks, postmortems, architecture docs, policies) from filesystem.
- Natural-language conversation workflows with contextual memory.

This spec defines:
- Minimal MVP schema for investigation workflows.
- JWT authentication and refresh-token lifecycle.
- Data relationships required for reasoning, ownership, escalation, and reporting.

MVP scope decisions:
- Single workspace (no tenant isolation yet).
- Single application role: `operations_engineer`.
- JWT access + refresh token model.
- Documentation remains filesystem-based in MVP (no document-index tables).

## 2. Functional Goals
The backend supports:
- Incident investigation and summary generation.
- Root-cause hypotheses with evidence references.
- Historical incident comparison.
- Ownership identification and escalation routing.
- Contextual conversation memory.
- Structured JSON assistant outputs.
- Full incident report generation.

## 3. Authentication Architecture (JWT)

### 3.1 Auth Model
- Password-based login with bcrypt hash verification.
- Access token: JWT (HS256), short-lived, used for `/api/v1/*` authorization.
- Refresh token: opaque token, long-lived, stored hashed in DB, rotated on refresh.

### 3.2 Token Policy
- Access token TTL: 15 minutes.
- Refresh token TTL: 7 days.
- Access token claims:
  - `sub`: user id.
  - `type`: `access`.
  - `role`: `operations_engineer`.
  - `iat`, `exp`, `jti`.
- Signing algorithm: HS256.

### 3.3 Auth Endpoints
1. `POST /auth/login`
- Input: username/email + password.
- Returns: `access_token`, `refresh_token`, `token_type`, `expires_in`, user profile.
- Persists refresh-token hash in `refresh_tokens`.

2. `POST /auth/refresh`
- Input: refresh token.
- Validates hash, expiry, and revocation.
- Rotates refresh token and returns new access + refresh tokens.

3. `POST /auth/logout`
- Input: refresh token.
- Revokes refresh token.

### 3.4 Authorization
- All `/api/v1/*` routes require `Authorization: Bearer <access_token>`.
- MVP role model is single-role only: `operations_engineer`.
- Auth checks enforce:
  - valid/tamper-free token,
  - token `type=access`,
  - active user,
  - role is `operations_engineer`.

## 4. Database Schema (MVP)

### 4.1 Identity and Ownership

#### `users`
Purpose: authenticated operators.

Columns:
- `id` (PK)
- `username` (unique, indexed)
- `email` (unique, indexed)
- `full_name` (nullable)
- `role` (`operations_engineer`; default `operations_engineer`)
- `password_hash`
- `is_active`
- `created_at`
- `updated_at`

#### `services`
Purpose: service catalog and ownership.

Columns:
- `id` (PK)
- `name` (unique)
- `tier` (`critical | high | medium | low`)
- `owner_user_id` (FK -> `users.id`)
- `repo_url` (nullable)
- `runbook_path` (nullable filesystem path)
- `created_at`

#### `service_dependencies`
Purpose: directed service dependency graph.

Columns:
- `id` (PK)
- `service_id` (FK -> `services.id`)
- `depends_on_service_id` (FK -> `services.id`)
- `created_at`

Constraints:
- unique (`service_id`, `depends_on_service_id`)

### 4.2 Incident Domain

#### `incidents`
Purpose: canonical incident records.

Columns:
- `id` (PK)
- `incident_key` (unique)
- `title`
- `status` (`open | investigating | mitigated | resolved`)
- `severity` (`sev1 | sev2 | sev3 | sev4`)
- `started_at`
- `resolved_at` (nullable)
- `summary` (nullable)
- `created_by_user_id` (FK -> `users.id`)
- `commander_user_id` (FK -> `users.id`, nullable)
- `created_at`
- `updated_at`

#### `incident_services`
Purpose: impacted services per incident (many-to-many).

Columns:
- `incident_id` (FK -> `incidents.id`)
- `service_id` (FK -> `services.id`)
- `impact_type` (`degraded | down | latency | errors`)
- `created_at`

Constraints:
- composite PK (`incident_id`, `service_id`)

#### `incident_tags`
Purpose: lightweight incident classification for historical matching.

Columns:
- `id` (PK)
- `incident_id` (FK -> `incidents.id`)
- `tag`
- `created_at`

#### `incident_evidence`
Purpose: unified incident timeline/evidence stream (metrics, alerts, notes, logs).

Columns:
- `id` (PK)
- `incident_id` (FK -> `incidents.id`)
- `service_id` (FK -> `services.id`, nullable)
- `event_type` (`metric | alert | note | log`)
- `event_time`
- `metric_name` (nullable)
- `metric_value` (numeric, nullable)
- `event_text` (nullable)
- `unit` (nullable)
- `tags_json` (jsonb, nullable)
- `metadata_json` (jsonb, nullable)
- `created_at`

#### `resolutions`
Purpose: historical fixes and root causes.

Columns:
- `id` (PK)
- `incident_id` (FK -> `incidents.id`)
- `resolution_summary`
- `root_cause`
- `actions_taken_json` (jsonb, nullable)
- `resolved_by_user_id` (FK -> `users.id`)
- `resolved_at`
- `created_at`

#### `escalation_contacts`
Purpose: service-level escalation routing.

Columns:
- `id` (PK)
- `service_id` (FK -> `services.id`)
- `name`
- `contact_type` (`email | slack | phone | pagerduty`)
- `contact_value`
- `priority_order`
- `is_primary`
- `created_at`

Constraints:
- unique (`service_id`, `priority_order`)

### 4.3 Conversation and Reasoning

#### `sessions`
Purpose: unified conversation sessions for chat.

Columns:
- `id` (UUID PK)
- `user_id` (FK -> `users.id`)
- `incident_id` (FK -> `incidents.id`, nullable)
- `session_type` (`chat`)
- `title` (nullable)
- `status` (`active | closed`)
- `created_at`
- `last_activity_at`

#### `messages`
Purpose: unified message history for all sessions.

Columns:
- `id` (UUID PK)
- `session_id` (FK -> `sessions.id`)
- `role` (`user | assistant | system`)
- `content_text`
- `structured_json` (jsonb, nullable)
- `created_at`

Indexes:
- (`session_id`, `created_at`)

#### `investigation_evidence`
Purpose: evidence references tied to assistant reasoning outputs.

Columns:
- `id` (PK)
- `session_id` (FK -> `sessions.id`)
- `message_id` (FK -> `messages.id`, nullable)
- `evidence_type` (`db_row | metric | incident | resolution | doc_file`)
- `evidence_ref`
- `evidence_source_table`
- `evidence_row_id`
- `excerpt` (nullable)
- `confidence_score` (numeric, nullable)
- `created_at`

### 4.4 Auth Session Management

#### `refresh_tokens`
Purpose: refresh-token lifecycle and revocation.

Columns:
- `id` (UUID PK)
- `user_id` (FK -> `users.id`)
- `token_hash` (unique)
- `issued_at`
- `expires_at`
- `revoked_at` (nullable)
- `replaced_by_token_id` (self FK, nullable)
- `user_agent` (nullable)
- `ip_address` (nullable)
- `created_at`

## 5. Final Table List (13)
- `users`
- `services`
- `service_dependencies`
- `incidents`
- `incident_services`
- `incident_tags`
- `incident_evidence`
- `resolutions`
- `escalation_contacts`
- `sessions`
- `messages`
- `investigation_evidence`
- `refresh_tokens`

## 6. Relationship Overview
- `users` 1:N `services` (`owner_user_id`)
- `users` 1:N `sessions`
- `users` 1:N `refresh_tokens`
- `services` N:M `services` via `service_dependencies` (directed)
- `services` N:M `incidents` via `incident_services`
- `services` 1:N `escalation_contacts`
- `incidents` 1:N `incident_tags`
- `incidents` 1:N `incident_evidence`
- `incidents` 1:N `resolutions`
- `sessions` 1:N `messages`
- `messages` 1:N `investigation_evidence` (nullable reference)

## 7. Structured Output Contract
Assistant responses should follow and persist this JSON shape in `messages.structured_json`:

```json
{
  "summary": "short narrative summary",
  "hypotheses": [
    {
      "cause": "possible root cause",
      "confidence": 0.75
    }
  ],
  "similar_incidents": [],
  "evidence": [],
  "owners": [],
  "escalation": [],
  "recommended_actions": [],
  "report": "optional detailed incident report"
}
```

## 8. Validation and Tests
- Auth tests: login, refresh rotation, logout revocation, invalid token rejection.
- Schema integrity tests: FK/unique/index constraints for ownership, dependencies, and escalation priority.
- Conversation tests: session/message ordering by (`session_id`, `created_at`), structured JSON persistence.
- Investigation tests: evidence linkage (`investigation_evidence`) and incident report composition across incident, evidence, ownership, escalation, and historical data.

## 9. Post-MVP (Deferred)
- Multi-tenant scoping.
- Document indexing/embeddings.
- Additional roles and fine-grained RBAC.
- SSO/OIDC.
