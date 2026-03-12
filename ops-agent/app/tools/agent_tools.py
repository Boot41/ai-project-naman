from __future__ import annotations

import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable
from uuid import UUID, uuid4

from app.tools.contracts import (
    make_error_response,
    make_no_data_response,
    make_success_response,
)
from app.tools.docs_search import search_docs as docs_search_fn

try:
    import psycopg
    from psycopg.rows import dict_row
except Exception:  # pragma: no cover - optional runtime dependency
    psycopg = None  # type: ignore[assignment]
    dict_row = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)
_LEGACY_INCIDENT_PATTERN = re.compile(r"^INC-(\d{3})$")
_INCIDENT_KEY_IN_QUERY = re.compile(r"\bINC-(?:\d{4}-\d{4}|\d+)\b", re.IGNORECASE)
_SERVICE_IN_QUERY = re.compile(r"\b([a-z0-9-]+-service)\b", re.IGNORECASE)


def _database_url() -> str:
    raw = (
        os.getenv("OPS_AGENT_DATABASE_URL", "").strip()
        or os.getenv("DATABASE_URL", "").strip()
    )
    if not raw:
        return ""
    # Allow server-style SQLAlchemy URLs.
    return raw.replace("postgresql+asyncpg://", "postgresql://", 1)


def _db_available() -> bool:
    return psycopg is not None and bool(_database_url())


def _json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _json_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_value(v) for v in value]
    return value


def _rows_json(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_json_value(dict(row)) for row in rows]


def _fetch_all(query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    if not _db_available():
        raise RuntimeError("database unavailable")
    assert psycopg is not None
    assert dict_row is not None
    with psycopg.connect(_database_url(), row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
            return [dict(row) for row in rows]


def _fetch_one(query: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    rows = _fetch_all(query, params)
    if not rows:
        return None
    return rows[0]


def _seed_dir() -> Path:
    configured = os.getenv("OPS_AGENT_SEED_DIR", "").strip()
    if configured:
        return Path(configured)

    local_default = Path(__file__).resolve().parents[3] / "server" / "seed_data"
    if local_default.exists():
        return local_default

    container_default = Path(__file__).resolve().parents[2] / "seed_data"
    return container_default


def _load_json(file_name: str) -> list[dict[str, Any]]:
    path = _seed_dir() / file_name
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    return payload if isinstance(payload, list) else []


@lru_cache
def _store() -> dict[str, list[dict[str, Any]]]:
    return {
        "incidents": _load_json("incidents.json"),
        "incident_services": _load_json("incident_services.json"),
        "incident_evidence": _load_json("incident_evidence.json"),
        "resolutions": _load_json("resolutions.json"),
        "services": _load_json("services.json"),
        "service_dependencies": _load_json("service_dependencies.json"),
        "escalation_contacts": _load_json("escalation_contacts.json"),
        "messages": _load_json("messages.json"),
        "users": _load_json("users.json"),
    }


def _resolve_incident_key(raw_key: str) -> str:
    match = _LEGACY_INCIDENT_PATTERN.match(raw_key.strip().upper())
    if match:
        legacy = int(match.group(1))
        if legacy >= 101:
            return f"INC-2026-{legacy - 100:04d}"
    return raw_key.strip().upper()


def _find_incident_seed(incident_key: str) -> dict[str, Any] | None:
    resolved_key = _resolve_incident_key(incident_key)
    for row in _store()["incidents"]:
        if str(row.get("incident_key", "")).upper() == resolved_key:
            return row
    return None


def _service_by_id_seed() -> dict[int, dict[str, Any]]:
    return {int(s["id"]): s for s in _store()["services"] if "id" in s}


def _service_by_name_seed() -> dict[str, dict[str, Any]]:
    return {str(s.get("name", "")).lower(): s for s in _store()["services"]}


def _user_by_id_seed() -> dict[int, dict[str, Any]]:
    return {int(u["id"]): u for u in _store()["users"] if "id" in u}


def _find_incident_db(incident_key: str) -> dict[str, Any] | None:
    return _fetch_one(
        """
        SELECT id, incident_key, title, status, severity, started_at, resolved_at,
               summary, created_by_user_id, commander_user_id, created_at, updated_at
        FROM incidents
        WHERE UPPER(incident_key) = %s
        """,
        (_resolve_incident_key(incident_key),),
    )


def _find_incident(incident_key: str) -> dict[str, Any] | None:
    try:
        incident = _find_incident_db(incident_key)
        if incident is not None:
            return _json_value(incident)
    except Exception as exc:
        logger.warning("incident_lookup_db_failed: %s", exc)
    return _find_incident_seed(incident_key)


def get_incident_by_key(incident_key: str) -> dict[str, Any]:
    source = "get_incident_by_key"
    try:
        incident = _find_incident(incident_key)
        if incident is None:
            return make_no_data_response(source, object_mode=True).model_dump()
        return make_success_response(source, incident).model_dump()
    except Exception as exc:
        return make_error_response(
            source, "INCIDENT_LOOKUP_FAILED", str(exc)
        ).model_dump()


def get_incident_services(incident_key: str) -> dict[str, Any]:
    source = "get_incident_services"
    try:
        incident = _find_incident(incident_key)
        if incident is None:
            return make_no_data_response(source).model_dump()

        incident_id = int(incident["id"])
        try:
            rows = _fetch_all(
                """
                SELECT isv.incident_id, isv.service_id, s.name AS service_name,
                       isv.impact_type, s.tier, s.owner_user_id
                FROM incident_services isv
                JOIN services s ON s.id = isv.service_id
                WHERE isv.incident_id = %s
                ORDER BY s.name
                """,
                (incident_id,),
            )
            if rows:
                return make_success_response(source, _rows_json(rows)).model_dump()
        except Exception:
            pass

        service_map = _service_by_id_seed()
        out: list[dict[str, Any]] = []
        for rel in _store()["incident_services"]:
            if rel.get("incident_id") != incident_id:
                continue
            service_id = int(rel.get("service_id"))
            service = service_map.get(service_id, {})
            out.append(
                {
                    "incident_id": incident_id,
                    "service_id": service_id,
                    "service_name": service.get("name"),
                    "impact_type": rel.get("impact_type"),
                    "tier": service.get("tier"),
                    "owner_user_id": service.get("owner_user_id"),
                }
            )
        return make_success_response(source, out).model_dump()
    except Exception as exc:
        return make_error_response(
            source, "INCIDENT_SERVICES_FAILED", str(exc)
        ).model_dump()


def get_incident_evidence(incident_key: str, limit: int = 200) -> dict[str, Any]:
    source = "get_incident_evidence"
    try:
        incident = _find_incident(incident_key)
        if incident is None:
            return make_no_data_response(source).model_dump()

        incident_id = int(incident["id"])
        safe_limit = max(1, int(limit))
        try:
            rows = _fetch_all(
                """
                SELECT e.id, e.incident_id, e.service_id, s.name AS service_name,
                       e.event_type, e.event_time, e.metric_name, e.metric_value,
                       e.event_text, e.unit, e.tags_json, e.metadata_json
                FROM incident_evidence e
                LEFT JOIN services s ON s.id = e.service_id
                WHERE e.incident_id = %s
                ORDER BY e.event_time
                LIMIT %s
                """,
                (incident_id, safe_limit),
            )
            if rows:
                return make_success_response(source, _rows_json(rows)).model_dump()

            overlap_rows = _fetch_all(
                """
                SELECT e.id, e.incident_id, e.service_id, s.name AS service_name,
                       e.event_type, e.event_time, e.metric_name, e.metric_value,
                       e.event_text, e.unit, e.tags_json, e.metadata_json,
                       e.incident_id AS related_incident_id,
                       TRUE AS inferred_from_service_overlap
                FROM incident_evidence e
                JOIN services s ON s.id = e.service_id
                WHERE e.service_id IN (
                    SELECT service_id FROM incident_services WHERE incident_id = %s
                )
                ORDER BY e.event_time
                LIMIT %s
                """,
                (incident_id, safe_limit),
            )
            if overlap_rows:
                return make_success_response(
                    source, _rows_json(overlap_rows)
                ).model_dump()
        except Exception:
            pass

        service_map = _service_by_id_seed()
        rows = [
            e
            for e in _store()["incident_evidence"]
            if e.get("incident_id") == incident_id
        ]
        if not rows:
            service_ids = {
                int(rel["service_id"])
                for rel in _store()["incident_services"]
                if rel.get("incident_id") == incident_id
            }
            rows = [
                {
                    **e,
                    "related_incident_id": e.get("incident_id"),
                    "inferred_from_service_overlap": True,
                }
                for e in _store()["incident_evidence"]
                if int(e.get("service_id", 0)) in service_ids
            ]

        rows.sort(key=lambda x: str(x.get("event_time", "")))
        data: list[dict[str, Any]] = []
        for row in rows[:safe_limit]:
            service = service_map.get(int(row.get("service_id", 0)), {})
            payload = dict(row)
            payload["service_name"] = service.get("name")
            data.append(payload)
        return make_success_response(source, data).model_dump()
    except Exception as exc:
        return make_error_response(
            source, "INCIDENT_EVIDENCE_FAILED", str(exc)
        ).model_dump()


def get_service_owner(service_name: str) -> dict[str, Any]:
    source = "get_service_owner"
    try:
        normalized = service_name.strip().lower()
        if not normalized:
            return make_no_data_response(source).model_dump()

        try:
            row = _fetch_one(
                """
                SELECT s.name AS service_name, s.owner_user_id,
                       u.full_name AS owner_name, u.email AS owner_email,
                       u.username AS owner_username
                FROM services s
                LEFT JOIN users u ON u.id = s.owner_user_id
                WHERE LOWER(s.name) = %s
                """,
                (normalized,),
            )
            if row:
                return make_success_response(source, [_json_value(row)]).model_dump()
        except Exception:
            pass

        service = _service_by_name_seed().get(normalized)
        if service is None:
            return make_no_data_response(source).model_dump()
        owner = _user_by_id_seed().get(int(service.get("owner_user_id", 0)), {})
        data = [
            {
                "service_name": service.get("name"),
                "owner_user_id": service.get("owner_user_id"),
                "owner_name": owner.get("full_name"),
                "owner_email": owner.get("email"),
                "owner_username": owner.get("username"),
            }
        ]
        return make_success_response(source, data).model_dump()
    except Exception as exc:
        return make_error_response(
            source, "SERVICE_OWNER_FAILED", str(exc)
        ).model_dump()


def get_service_dependencies(service_name: str) -> dict[str, Any]:
    source = "get_service_dependencies"
    try:
        normalized = service_name.strip().lower()
        if not normalized:
            return make_no_data_response(source).model_dump()

        try:
            rows = _fetch_all(
                """
                SELECT s.name AS service_name,
                       d.depends_on_service_id,
                       dep.name AS depends_on_service_name,
                       dep.tier AS depends_on_service_tier
                FROM services s
                JOIN service_dependencies d ON d.service_id = s.id
                JOIN services dep ON dep.id = d.depends_on_service_id
                WHERE LOWER(s.name) = %s
                ORDER BY dep.name
                """,
                (normalized,),
            )
            if rows:
                return make_success_response(source, _rows_json(rows)).model_dump()
        except Exception:
            pass

        service = _service_by_name_seed().get(normalized)
        if service is None:
            return make_no_data_response(source).model_dump()

        service_map = _service_by_id_seed()
        service_id = int(service["id"])
        out: list[dict[str, Any]] = []
        for dep in _store()["service_dependencies"]:
            if dep.get("service_id") != service_id:
                continue
            depends_on_id = int(dep.get("depends_on_service_id"))
            depends_on = service_map.get(depends_on_id, {})
            out.append(
                {
                    "service_name": service.get("name"),
                    "depends_on_service_id": depends_on_id,
                    "depends_on_service_name": depends_on.get("name"),
                    "depends_on_service_tier": depends_on.get("tier"),
                }
            )
        return make_success_response(source, out).model_dump()
    except Exception as exc:
        return make_error_response(
            source, "SERVICE_DEPENDENCIES_FAILED", str(exc)
        ).model_dump()


def get_similar_incidents(incident_key: str, limit: int = 5) -> dict[str, Any]:
    source = "get_similar_incidents"
    try:
        base = _find_incident(incident_key)
        if base is None:
            return make_no_data_response(source).model_dump()

        base_id = int(base["id"])
        base_severity = str(base.get("severity", ""))
        safe_limit = max(1, int(limit))

        try:
            base_service_rows = _fetch_all(
                "SELECT service_id FROM incident_services WHERE incident_id = %s",
                (base_id,),
            )
            base_service_ids = [int(r["service_id"]) for r in base_service_rows]

            candidate_rows = _fetch_all(
                """
                SELECT i.id, i.incident_key, i.title, i.status, i.severity,
                       COALESCE(
                         SUM(CASE WHEN isv.service_id = ANY(%s) THEN 1 ELSE 0 END),
                         0
                       ) AS service_overlap_count
                FROM incidents i
                LEFT JOIN incident_services isv ON isv.incident_id = i.id
                WHERE i.id <> %s
                GROUP BY i.id
                """,
                (base_service_ids or [0], base_id),
            )

            out: list[dict[str, Any]] = []
            for row in candidate_rows:
                overlap = int(row.get("service_overlap_count") or 0)
                severity = str(row.get("severity") or "")
                if overlap == 0 and severity != base_severity:
                    continue
                out.append(
                    {
                        "incident_key": row.get("incident_key"),
                        "title": row.get("title"),
                        "status": row.get("status"),
                        "severity": severity,
                        "service_overlap_count": overlap,
                        "similarity_reason": "service_overlap"
                        if overlap > 0
                        else "same_severity",
                    }
                )

            out.sort(
                key=lambda x: (
                    -int(x.get("service_overlap_count", 0)),
                    str(x.get("incident_key", "")),
                )
            )
            if out:
                return make_success_response(source, out[:safe_limit]).model_dump()
        except Exception:
            pass

        base_services = {
            int(r["service_id"])
            for r in _store()["incident_services"]
            if r.get("incident_id") == base_id
        }
        out = []
        for incident in _store()["incidents"]:
            if incident["id"] == base_id:
                continue
            inc_services = {
                int(r["service_id"])
                for r in _store()["incident_services"]
                if r.get("incident_id") == incident["id"]
            }
            overlap = len(base_services & inc_services)
            if overlap == 0 and incident.get("severity") != base.get("severity"):
                continue
            out.append(
                {
                    "incident_key": incident.get("incident_key"),
                    "title": incident.get("title"),
                    "status": incident.get("status"),
                    "severity": incident.get("severity"),
                    "service_overlap_count": overlap,
                    "similarity_reason": "service_overlap"
                    if overlap > 0
                    else "same_severity",
                }
            )
        out.sort(
            key=lambda x: (
                -int(x.get("service_overlap_count", 0)),
                str(x.get("incident_key", "")),
            )
        )
        return make_success_response(source, out[:safe_limit]).model_dump()
    except Exception as exc:
        return make_error_response(
            source, "SIMILAR_INCIDENTS_FAILED", str(exc)
        ).model_dump()


def get_resolutions(incident_key: str) -> dict[str, Any]:
    source = "get_resolutions"
    try:
        incident = _find_incident(incident_key)
        if incident is None:
            return make_no_data_response(source).model_dump()

        incident_id = int(incident["id"])
        try:
            rows = _fetch_all(
                """
                SELECT id, incident_id, resolution_summary, root_cause,
                       actions_taken_json, resolved_by_user_id,
                       resolved_at, created_at
                FROM resolutions
                WHERE incident_id = %s
                ORDER BY resolved_at DESC
                """,
                (incident_id,),
            )
            if rows:
                return make_success_response(source, _rows_json(rows)).model_dump()
        except Exception:
            pass

        rows = [
            r for r in _store()["resolutions"] if r.get("incident_id") == incident_id
        ]
        return make_success_response(source, rows).model_dump()
    except Exception as exc:
        return make_error_response(source, "RESOLUTIONS_FAILED", str(exc)).model_dump()


def get_escalation_contacts(service_name: str) -> dict[str, Any]:
    source = "get_escalation_contacts"
    try:
        normalized = service_name.strip().lower()
        if not normalized:
            return make_no_data_response(source).model_dump()

        try:
            rows = _fetch_all(
                """
                SELECT e.id, e.service_id, e.name, e.contact_type, e.contact_value,
                       e.priority_order, e.is_primary, s.name AS service_name
                FROM escalation_contacts e
                JOIN services s ON s.id = e.service_id
                WHERE LOWER(s.name) = %s
                ORDER BY e.priority_order
                """,
                (normalized,),
            )
            if rows:
                return make_success_response(source, _rows_json(rows)).model_dump()
        except Exception:
            pass

        service = _service_by_name_seed().get(normalized)
        if service is None:
            return make_no_data_response(source).model_dump()
        rows = [
            dict(c)
            for c in _store()["escalation_contacts"]
            if c.get("service_id") == service.get("id")
        ]
        rows.sort(key=lambda x: int(x.get("priority_order", 999)))
        for row in rows:
            row["service_name"] = service.get("name")
        return make_success_response(source, rows).model_dump()
    except Exception as exc:
        return make_error_response(
            source, "ESCALATION_CONTACTS_FAILED", str(exc)
        ).model_dump()


def load_session_messages(session_id: str, limit: int = 30) -> dict[str, Any]:
    source = "load_session_messages"
    try:
        safe_limit = max(1, int(limit))
        try:
            rows = _fetch_all(
                """
                SELECT id, session_id, role, content_text, structured_json, created_at
                FROM messages
                WHERE session_id = %s::uuid
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (str(session_id), safe_limit),
            )
            if rows:
                rows.reverse()
                return make_success_response(source, _rows_json(rows)).model_dump()
        except Exception:
            pass

        rows = [
            m
            for m in _store()["messages"]
            if str(m.get("session_id")) == str(session_id)
        ]
        rows.sort(key=lambda x: str(x.get("id", "")))
        return make_success_response(source, rows[-safe_limit:]).model_dump()
    except Exception as exc:
        return make_error_response(
            source, "SESSION_MESSAGES_FAILED", str(exc)
        ).model_dump()


def save_assistant_message(
    session_id: str,
    content_text: str,
    structured_json: dict[str, Any],
) -> dict[str, Any]:
    source = "save_assistant_message"
    try:
        payload = {
            "id": str(uuid4()),
            "session_id": session_id,
            "role": "assistant",
            "content_text": content_text,
            "structured_json": structured_json,
        }
        return make_success_response(source, payload).model_dump()
    except Exception as exc:
        return make_error_response(
            source, "SAVE_ASSISTANT_MESSAGE_FAILED", str(exc)
        ).model_dump()


def get_investigation_bundle(
    query: str,
    session_id: str,
    incident_key: str | None = None,
    service_name: str | None = None,
    docs_category: str | None = None,
    top_k_docs: int = 5,
) -> dict[str, Any]:
    source = "get_investigation_bundle"
    try:
        resolved_incident_key = _resolve_incident_key_from_inputs(
            query=query, incident_key=incident_key
        )
        resolved_service_name = _resolve_service_name_from_inputs(
            query=query, service_name=service_name
        )

        docs_service = (
            resolved_service_name
            if docs_category not in {"policies", "architecture"}
            else None
        )
        jobs: list[tuple[str, Callable[[], dict[str, Any]]]] = [
            ("load_session_messages", lambda: load_session_messages(session_id, limit=30)),
            (
                "search_docs",
                lambda: search_docs(
                    query=query,
                    top_k=max(1, int(top_k_docs)),
                    category=docs_category,
                    service=docs_service,
                ),
            ),
        ]
        if resolved_incident_key:
            jobs.extend(
                [
                    (
                        "get_incident_by_key",
                        lambda: get_incident_by_key(resolved_incident_key),
                    ),
                    (
                        "get_incident_services",
                        lambda: get_incident_services(resolved_incident_key),
                    ),
                    (
                        "get_incident_evidence",
                        lambda: get_incident_evidence(resolved_incident_key, limit=200),
                    ),
                    (
                        "get_similar_incidents",
                        lambda: get_similar_incidents(resolved_incident_key, limit=5),
                    ),
                    (
                        "get_resolutions",
                        lambda: get_resolutions(resolved_incident_key),
                    ),
                ]
            )
        if resolved_service_name:
            jobs.extend(
                [
                    (
                        "get_service_owner",
                        lambda: get_service_owner(resolved_service_name),
                    ),
                    (
                        "get_service_dependencies",
                        lambda: get_service_dependencies(resolved_service_name),
                    ),
                    (
                        "get_escalation_contacts",
                        lambda: get_escalation_contacts(resolved_service_name),
                    ),
                ]
            )

        raw_results: dict[str, dict[str, Any]] = {}
        with ThreadPoolExecutor(max_workers=min(10, len(jobs) or 1)) as executor:
            futures = {executor.submit(fn): name for name, fn in jobs}
            for future in as_completed(futures):
                name = futures[future]
                try:
                    raw_results[name] = future.result()
                except Exception as exc:
                    raw_results[name] = make_error_response(
                        name, "TOOL_EXECUTION_FAILED", str(exc)
                    ).model_dump()

        service_names: list[str] = []
        base_service_rows = _tool_rows(raw_results.get("get_incident_services"))
        for row in base_service_rows:
            name = str(row.get("service_name") or "").strip().lower()
            if name:
                service_names.append(name)
        if resolved_service_name:
            service_names.append(resolved_service_name)
        unique_services = list(dict.fromkeys(service_names))[:5]
        for name in unique_services:
            owner_key = f"get_service_owner:{name}"
            esc_key = f"get_escalation_contacts:{name}"
            dep_key = f"get_service_dependencies:{name}"
            raw_results[owner_key] = get_service_owner(name)
            raw_results[esc_key] = get_escalation_contacts(name)
            raw_results[dep_key] = get_service_dependencies(name)

        merged = {
            "incident": _tool_rows(raw_results.get("get_incident_by_key")),
            "services": _merge_rows(
                [
                    _tool_rows(raw_results.get("get_incident_services")),
                    _tool_rows(raw_results.get("get_service_owner")),
                    _tool_rows(raw_results.get("get_service_dependencies")),
                    _tool_rows(raw_results.get("get_escalation_contacts")),
                    *[
                        _tool_rows(raw_results.get(f"get_service_owner:{name}"))
                        for name in unique_services
                    ],
                    *[
                        _tool_rows(raw_results.get(f"get_service_dependencies:{name}"))
                        for name in unique_services
                    ],
                    *[
                        _tool_rows(raw_results.get(f"get_escalation_contacts:{name}"))
                        for name in unique_services
                    ],
                ]
            ),
            "evidence": _merge_rows(
                [
                    _tool_rows(raw_results.get("get_incident_evidence")),
                    _tool_rows(raw_results.get("get_resolutions")),
                ]
            ),
            "docs": _tool_rows(raw_results.get("search_docs")),
            "historical_incidents": _tool_rows(raw_results.get("get_similar_incidents")),
            "resolutions": _tool_rows(raw_results.get("get_resolutions")),
            "session_history": _tool_rows(raw_results.get("load_session_messages")),
        }

        return make_success_response(
            source,
            {
                "resolved_incident_key": resolved_incident_key,
                "resolved_service_name": resolved_service_name,
                "merged": merged,
                "raw_results": raw_results,
            },
        ).model_dump()
    except Exception as exc:
        return make_error_response(source, "INVESTIGATION_BUNDLE_FAILED", str(exc)).model_dump()


def search_docs(
    query: str,
    top_k: int = 5,
    category: str | None = None,
    service: str | None = None,
) -> dict[str, Any]:
    return docs_search_fn(query=query, top_k=top_k, category=category, service=service)


def _tool_rows(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not payload or not payload.get("ok", False):
        return []
    data = payload.get("data", [])
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def _merge_rows(chunks: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for rows in chunks:
        for row in rows:
            sig = _record_signature(row)
            if sig in seen:
                continue
            seen.add(sig)
            merged.append(row)
    return merged


def _record_signature(item: dict[str, Any]) -> str:
    for key in ("id", "event_id", "doc_id", "incident_key", "service_name"):
        value = item.get(key)
        if value:
            return f"{key}:{value}"
    return str(sorted(item.items()))


def _resolve_incident_key_from_inputs(*, query: str, incident_key: str | None) -> str | None:
    if incident_key and incident_key.strip():
        return _resolve_incident_key(incident_key)
    match = _INCIDENT_KEY_IN_QUERY.search(query)
    if match:
        return _resolve_incident_key(match.group(0))
    return None


def _resolve_service_name_from_inputs(*, query: str, service_name: str | None) -> str | None:
    if service_name and service_name.strip():
        return service_name.strip().lower()
    match = _SERVICE_IN_QUERY.search(query)
    if match:
        return match.group(1).lower()
    return None
