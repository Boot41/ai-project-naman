from __future__ import annotations

import re

from app.tools.agent_tools import (
    get_escalation_contacts,
    get_incident_by_key,
    get_incident_services,
    get_resolutions,
    get_service_owner,
    get_similar_incidents,
    search_docs,
)

_INCIDENT_KEY_PATTERN = re.compile(r"\bINC-(?:\d{4}-\d{4}|\d+)\b", re.IGNORECASE)
_SERVICE_NAME_PATTERN = re.compile(r"\b([a-z0-9-]+-service)\b", re.IGNORECASE)


def enrich_owner_escalation(payload: dict, incident_key: str | None, summary: str) -> dict:
    normalized = dict(payload)
    owners = _coerce_owners(normalized.get("owners"))
    escalation = _coerce_escalation(normalized.get("escalation"))
    owner_services = {row["service_name"] for row in owners}
    escalation_services = {row["service_name"] for row in escalation}

    service_names: list[str] = []
    if incident_key:
        services_resp = get_incident_services(incident_key)
        if services_resp.get("ok"):
            for row in services_resp.get("data", []):
                if isinstance(row, dict):
                    name = str(row.get("service_name") or "").strip().lower()
                    if name:
                        service_names.append(name)
    if not service_names:
        service_names = [s.lower() for s in re.findall(r"\b[a-z0-9-]+-service\b", summary)]

    for service_name in list(dict.fromkeys(service_names))[:5]:
        if service_name not in owner_services:
            owner_resp = get_service_owner(service_name)
            if owner_resp.get("ok"):
                rows = owner_resp.get("data", [])
                if isinstance(rows, list) and rows:
                    row0 = rows[0] if isinstance(rows[0], dict) else {}
                    owner_value = (
                        str(row0.get("owner_name") or "").strip()
                        or str(row0.get("owner_username") or "").strip()
                        or str(row0.get("owner_email") or "").strip()
                        or None
                    )
                    owners.append({"service_name": service_name, "owner": owner_value})
                    owner_services.add(service_name)

        if service_name not in escalation_services:
            esc_resp = get_escalation_contacts(service_name)
            contacts: list[str] = []
            if esc_resp.get("ok"):
                for row in esc_resp.get("data", []):
                    if not isinstance(row, dict):
                        continue
                    name = str(row.get("name") or "").strip()
                    ctype = str(row.get("contact_type") or "").strip()
                    cval = str(row.get("contact_value") or "").strip()
                    if name and cval:
                        contacts.append(f"{name} ({ctype}: {cval})" if ctype else f"{name} ({cval})")
            if contacts:
                escalation.append({"service_name": service_name, "contacts": contacts})
                escalation_services.add(service_name)

    normalized["owners"] = owners
    normalized["escalation"] = escalation
    return normalized


def _coerce_owners(value: object) -> list[dict]:
    out: list[dict] = []
    if not isinstance(value, list):
        return out
    for item in value:
        if not isinstance(item, dict):
            continue
        service_name = str(item.get("service_name") or "").strip()
        if not service_name:
            continue
        owner = item.get("owner")
        owner_text = str(owner).strip() if isinstance(owner, str) else None
        if owner_text and owner_text.lower().startswith("user id"):
            owner_text = None
        out.append({"service_name": service_name, "owner": owner_text})
    return out


def _coerce_escalation(value: object) -> list[dict]:
    out: list[dict] = []
    if not isinstance(value, list):
        return out
    for item in value:
        if not isinstance(item, dict):
            continue
        service_name = str(item.get("service_name") or "").strip()
        if not service_name:
            continue
        contacts = [
            str(contact).strip()
            for contact in (item.get("contacts") or [])
            if str(contact).strip()
        ]
        out.append({"service_name": service_name, "contacts": contacts})
    return out


def enrich_investigation_facts(payload: dict, *, query: str, incident_key: str | None) -> dict:
    """
    Backfill missing high-value facts from tools for root-cause and comparison queries.
    This prevents inconclusive responses when DB/seed already has the needed records.
    """
    normalized = dict(payload)
    query_lower = query.lower()
    resolved_incident_key = (incident_key or _extract_incident_key(query) or "").strip().upper()
    resolved_service_name = _extract_service_name(query)
    evidence = [row for row in (normalized.get("evidence") or []) if isinstance(row, dict)]
    hypotheses = [row for row in (normalized.get("hypotheses") or []) if isinstance(row, dict)]
    similar_incidents = [
        row for row in (normalized.get("similar_incidents") or []) if isinstance(row, dict)
    ]
    owners = [row for row in (normalized.get("owners") or []) if isinstance(row, dict)]
    escalation = [row for row in (normalized.get("escalation") or []) if isinstance(row, dict)]

    if resolved_incident_key:
        incident_resp = get_incident_by_key(resolved_incident_key)
        if incident_resp.get("ok"):
            incident_row = _first_row(incident_resp.get("data"))
            if incident_row:
                title = str(incident_row.get("title") or "").strip()
                summary = str(incident_row.get("summary") or "").strip()
                snippet = f"{resolved_incident_key}: {title}. {summary}".strip()
                _add_evidence(
                    evidence,
                    ref=f"incident:{resolved_incident_key}",
                    source="db",
                    snippet=snippet,
                )

    if resolved_incident_key and any(token in query_lower for token in ("root cause", "likely cause", "cause", "why")):
        resolution_resp = get_resolutions(resolved_incident_key)
        if resolution_resp.get("ok"):
            resolution_row = _first_row(resolution_resp.get("data"))
            if resolution_row:
                resolution_id = str(resolution_row.get("id") or "primary")
                root_cause = str(resolution_row.get("root_cause") or "").strip()
                resolution_summary = str(resolution_row.get("resolution_summary") or "").strip()
                if root_cause:
                    _add_evidence(
                        evidence,
                        ref=f"resolution:{resolution_id}",
                        source="db",
                        snippet=f"Root cause identified: {root_cause}",
                    )
                    if not hypotheses:
                        hypotheses.append(
                            {
                                "cause": root_cause.rstrip("."),
                                "confidence": 0.9,
                                "supporting_evidence_refs": [f"resolution:{resolution_id}"],
                                "counter_evidence_refs": [],
                                "reasoning_summary": "Derived from incident resolution record.",
                            }
                        )
                if resolution_summary:
                    _add_evidence(
                        evidence,
                        ref=f"resolution_summary:{resolution_id}",
                        source="db",
                        snippet=f"Resolution summary: {resolution_summary}",
                    )

    if resolved_incident_key and any(token in query_lower for token in ("compare", "similar", "historical")):
        similar_resp = get_similar_incidents(resolved_incident_key, limit=5)
        if similar_resp.get("ok"):
            rows = _rows(similar_resp.get("data"))
            if rows:
                if not similar_incidents:
                    similar_incidents.extend(
                        [
                            {
                                "incident_key": str(row.get("incident_key") or "").strip().upper(),
                                "similarity_reason": str(row.get("similarity_reason") or "").strip(),
                            }
                            for row in rows
                            if str(row.get("incident_key") or "").strip()
                        ]
                    )
                for row in rows[:3]:
                    ikey = str(row.get("incident_key") or "").strip().upper()
                    reason = str(row.get("similarity_reason") or "").strip() or "similar incident"
                    if ikey:
                        _add_evidence(
                            evidence,
                            ref=f"historical:{ikey}",
                            source="db",
                            snippet=f"Similar incident {ikey} identified ({reason}).",
                        )

    docs_intent = _is_docs_guidance_query(query_lower)
    docs_category = _resolve_docs_category(query_lower)
    if docs_intent:
        docs_service_filter = (
            resolved_service_name
            if docs_category not in {"policies", "architecture"}
            else None
        )
        docs_resp = search_docs(
            query=query,
            top_k=5,
            category=docs_category,
            service=docs_service_filter,
        )
        if docs_resp.get("ok"):
            for row in _rows(docs_resp.get("data"))[:4]:
                doc_id = str(row.get("doc_id") or row.get("id") or "").strip()
                source_file = str(row.get("source_file") or "").strip()
                snippet = (
                    str(row.get("content_snippet") or "").strip()
                    or str(row.get("finding") or "").strip()
                    or str(row.get("content") or "").strip()
                )
                if not snippet:
                    continue
                ref = f"doc:{doc_id}" if doc_id else f"doc:{source_file or 'guidance'}"
                _add_evidence(evidence, ref=ref, source="docs", snippet=snippet)

    if resolved_service_name:
        owner_resp = get_service_owner(resolved_service_name)
        if owner_resp.get("ok"):
            owner_row = _first_row(owner_resp.get("data"))
            if owner_row:
                owner_name = (
                    str(owner_row.get("owner_name") or "").strip()
                    or str(owner_row.get("owner_username") or "").strip()
                    or str(owner_row.get("owner_email") or "").strip()
                    or None
                )
                if not any(
                    str(row.get("service_name") or "").strip().lower() == resolved_service_name
                    for row in owners
                ):
                    owners.append({"service_name": resolved_service_name, "owner": owner_name})
        esc_resp = get_escalation_contacts(resolved_service_name)
        if esc_resp.get("ok"):
            contacts: list[str] = []
            for row in _rows(esc_resp.get("data")):
                name = str(row.get("name") or "").strip()
                ctype = str(row.get("contact_type") or "").strip()
                cval = str(row.get("contact_value") or "").strip()
                if name and cval:
                    contacts.append(f"{name} ({ctype}: {cval})" if ctype else f"{name} ({cval})")
            if contacts and not any(
                str(row.get("service_name") or "").strip().lower() == resolved_service_name
                for row in escalation
            ):
                escalation.append({"service_name": resolved_service_name, "contacts": contacts})

    normalized["evidence"] = evidence
    normalized["hypotheses"] = hypotheses
    normalized["similar_incidents"] = similar_incidents
    normalized["owners"] = owners
    normalized["escalation"] = escalation
    return normalized


def _rows(value: object) -> list[dict]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        return [value]
    return []


def _first_row(value: object) -> dict | None:
    rows = _rows(value)
    return rows[0] if rows else None


def _add_evidence(evidence: list[dict], *, ref: str, source: str, snippet: str) -> None:
    normalized_ref = ref.strip()
    normalized_snippet = snippet.strip()
    if not normalized_ref or not normalized_snippet:
        return
    signatures = {str(item.get("ref") or "").strip() for item in evidence if isinstance(item, dict)}
    if normalized_ref in signatures:
        return
    evidence.append(
        {
            "ref": normalized_ref,
            "source": source,
            "snippet": _truncate_sentence(normalized_snippet, 260),
        }
    )


def _extract_incident_key(text: str) -> str | None:
    match = _INCIDENT_KEY_PATTERN.search(text)
    return match.group(0).upper() if match else None


def _extract_service_name(text: str) -> str | None:
    match = _SERVICE_NAME_PATTERN.search(text)
    return match.group(1).lower() if match else None


def _is_docs_guidance_query(query_lower: str) -> bool:
    return any(
        token in query_lower
        for token in (
            "policy",
            "runbook",
            "postmortem",
            "architecture",
            "what does",
            "guidance",
            "troubleshoot",
            "mitigation",
            "mitigate",
            "immediate",
        )
    )


def _resolve_docs_category(query_lower: str) -> str | None:
    if "policy" in query_lower:
        return "policies"
    if "runbook" in query_lower:
        return "runbooks"
    if "postmortem" in query_lower:
        return "postmortems"
    if "architecture" in query_lower or "dependency" in query_lower:
        return "architecture"
    return None


def _truncate_sentence(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text.strip()

    sentence_end = re.search(r"[.!?](?=\s|$)", text[limit : limit + 140])
    if sentence_end:
        end = limit + sentence_end.end()
        return text[:end].strip()

    cut = text[:limit]
    endings = list(re.finditer(r"[.!?](?=\s|$)", cut))
    if endings and endings[-1].end() >= int(limit * 0.55):
        return cut[: endings[-1].end()].strip()

    boundary = cut.rfind(" ")
    if boundary > 0:
        return cut[:boundary].strip()
    return cut.strip()
