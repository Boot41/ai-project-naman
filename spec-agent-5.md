# Spec Agent 5: Tooling, Data Contracts, and Retrieval Layer

## 1. Purpose

Define all tool interfaces, DB/document retrieval behavior, and validation contracts used by agents.

## 2. Common Tool Response Envelope

All tools return:

```json
{
  "ok": true,
  "data": [],
  "error": null,
  "source": "tool_name"
}
```

No-data behavior:

- `ok=true`, `data=[]` (or `{}`), `error=null`.
- `ok=false` only for execution/validation failures.

## 3. Database Tools

### `get_incident_by_key(incident_key: str)`

Returns: `id`, `incident_key`, `title`, `status`, `severity`, `started_at`, `resolved_at`, `summary`, `commander_user_id`.

### `get_incident_services(incident_key: str)`

Returns: `service_id`, `service_name`, `impact_type`, `tier`, `owner_user_id`, `runbook_path`.

### `get_incident_evidence(incident_key: str, limit: int=200)`

Returns: `id`, `service_id`, `event_type`, `event_time`, `metric_name`, `metric_value`, `unit`, `event_text`, `tags_json`, `metadata_json`.

### `get_service_owner(service_name: str)`

Returns: `service_name`, `owner_user_id`, `owner_username`, `owner_email`, `owner_full_name`, `owner_role`.

### `get_service_dependencies(service_name: str)`

Returns dependency edges: `service_name`, `depends_on_service_name`.

### `get_similar_incidents(incident_key: str, limit: int=5)`

Returns: `incident_key`, `title`, `severity`, `status`, `summary`, `similarity_reason`.

Similarity guidance for implementation:

- Compare overlapping impacted services.
- Compare evidence tags/event types.
- Compare severity and status patterns.
- Prefer recent incidents when ties occur.

### `get_resolutions(incident_key: str)`

Returns: `resolution_summary`, `root_cause`, `actions_taken_json`, `resolved_at`, `resolved_by_user_id`.

### `get_escalation_contacts(service_name: str)`

Returns: `name`, `contact_type`, `contact_value`, `priority_order`, `is_primary`.

### `load_session_messages(session_id: uuid, limit: int=30)`

Returns: `id`, `role`, `content_text`, `structured_json`, `created_at`.

### `save_assistant_message(session_id: uuid, content_text: str, structured_json: object)`

Persists assistant output and returns `message_id`.

## 4. Docs Tool

### `search_docs(query: str, top_k: int=5, category: str|null=null, service: str|null=null)`

Source index: `ops-agent/resources/index.json`.

Returns ranked documents:

- `doc_id`
- `category`
- `source_file`
- `service` (nullable)
- `tags`
- `content_snippet`
- `score`

## 5. Retrieval Ranking Rules

- Pre-filter by `category` and `service` when provided.
- Score by query-term overlap with title/tags/snippets.
- Boost same-service documents.
- Return top `k` after sorting by score desc.

## 6. Validation Rules

- Timestamps: ISO-8601 UTC.
- `incident_key`: `^INC-[0-9]+$` when provided.
- `confidence`: `[0.0, 1.0]`.
- Never hide errors in free text; use `error` object.

## 7. Security and Access Rules

- Require authenticated user context for all protected tool execution.
- Scope session-message retrieval by `session_id` owned by current user.
- Return sanitized error messages.

## 8. Logging

For each tool call emit:

```json
{
  "trace_id": "string",
  "tool": "string",
  "args_hash": "string",
  "ok": true,
  "result_count": 0,
  "latency_ms": 0,
  "error_code": "string|null"
}
```

## 9. Acceptance Criteria

- All tools conform to response envelope.
- Empty-result behavior is consistent.
- Inputs validated before execution.
- Output fields map to database/resources accurately.

Implementation mapping:

- ADK tool wrappers: `ops-agent/app/tools/agent_tools.py`
- Database tool exports: `ops-agent/app/tools/database_tools.py`
- Docs retrieval: `ops-agent/app/tools/docs_search.py`
- Parallel retrieval merge: `ops-agent/app/orchestration/retrieval.py`
