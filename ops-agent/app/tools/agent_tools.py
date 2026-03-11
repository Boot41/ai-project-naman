from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.tools.contracts import (
    make_error_response,
    make_no_data_response,
    make_success_response,
)
from app.tools.docs_search import search_docs as docs_search_fn

_LEGACY_INCIDENT_PATTERN = re.compile(r"^INC-(\d{3})$")


def _seed_dir() -> Path:
    configured = os.getenv("OPS_AGENT_SEED_DIR", "").strip()
    if configured:
        return Path(configured)

    # Local dev default: repo-root/server/seed_data
    local_default = Path(__file__).resolve().parents[3] / "server" / "seed_data"
    if local_default.exists():
        return local_default

    # Container fallback: if seed data is copied/mounted under /app/seed_data.
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


def _find_incident(incident_key: str) -> dict[str, Any] | None:
    resolved_key = _resolve_incident_key(incident_key)
    for row in _store()["incidents"]:
        if str(row.get("incident_key", "")).upper() == resolved_key:
            return row
    return None


def _service_by_id() -> dict[int, dict[str, Any]]:
    return {int(s["id"]): s for s in _store()["services"] if "id" in s}


def _service_by_name() -> dict[str, dict[str, Any]]:
    return {str(s.get("name", "")).lower(): s for s in _store()["services"]}


def _user_by_id() -> dict[int, dict[str, Any]]:
    return {int(u["id"]): u for u in _store()["users"] if "id" in u}


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

        service_map = _service_by_id()
        out: list[dict[str, Any]] = []
        incident_id = incident["id"]
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

        service_map = _service_by_id()
        incident_id = incident["id"]
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
        data = []
        for row in rows[: max(1, limit)]:
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
        service = _service_by_name().get(service_name.lower())
        if service is None:
            return make_no_data_response(source).model_dump()

        owner = _user_by_id().get(int(service.get("owner_user_id", 0)), {})
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
        service = _service_by_name().get(service_name.lower())
        if service is None:
            return make_no_data_response(source).model_dump()

        service_map = _service_by_id()
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

        base_services = {
            int(r["service_id"])
            for r in _store()["incident_services"]
            if r.get("incident_id") == base["id"]
        }
        out: list[dict[str, Any]] = []
        for incident in _store()["incidents"]:
            if incident["id"] == base["id"]:
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
        return make_success_response(source, out[: max(1, limit)]).model_dump()
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
        rows = [
            r for r in _store()["resolutions"] if r.get("incident_id") == incident["id"]
        ]
        return make_success_response(source, rows).model_dump()
    except Exception as exc:
        return make_error_response(source, "RESOLUTIONS_FAILED", str(exc)).model_dump()


def get_escalation_contacts(service_name: str) -> dict[str, Any]:
    source = "get_escalation_contacts"
    try:
        service = _service_by_name().get(service_name.lower())
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
        rows = [
            m
            for m in _store()["messages"]
            if str(m.get("session_id")) == str(session_id)
        ]
        rows.sort(key=lambda x: str(x.get("id", "")))
        return make_success_response(source, rows[-max(1, limit) :]).model_dump()
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


def search_docs(
    query: str,
    top_k: int = 5,
    category: str | None = None,
    service: str | None = None,
) -> dict[str, Any]:
    return docs_search_fn(query=query, top_k=top_k, category=category, service=service)
