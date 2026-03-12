from __future__ import annotations

import re
from typing import Any

_RAW_OWNER_ID_PATTERN = re.compile(r"\buser\s*id\s*\d+\b(?:\s*\([^)]*\))?", re.IGNORECASE)


def build_presentation(
    structured: dict[str, object] | None,
    *,
    fallback_summary: str | None = None,
) -> dict[str, object]:
    payload = dict(structured or {})
    status = _status_value(payload)
    summary = (
        _first_non_empty_str(payload.get("summary"), fallback_summary) or "No summary available."
    )
    report = _coerce_str(payload.get("report"))
    hypotheses = _coerce_list(payload.get("hypotheses"))
    evidence = _coerce_list(payload.get("evidence"))
    owners = _coerce_list(payload.get("owners"))
    escalation = _coerce_list(payload.get("escalation"))
    actions = [
        str(item).strip()
        for item in _coerce_list(payload.get("recommended_actions"))
        if str(item).strip()
    ]

    blocks: list[dict[str, object]] = [{"type": "markdown", "title": "Summary", "content": summary}]

    hypothesis_rows: list[list[str]] = []
    for item in hypotheses:
        if not isinstance(item, dict):
            continue
        cause = _coerce_str(item.get("cause"))
        confidence = item.get("confidence")
        refs = item.get("supporting_evidence_refs")
        if not cause:
            continue
        confidence_text = ""
        if isinstance(confidence, (int, float)):
            confidence_text = f"{float(confidence):.2f}"
        refs_text = ", ".join(str(ref) for ref in _coerce_list(refs))
        hypothesis_rows.append([cause, confidence_text, refs_text])
    if hypothesis_rows:
        blocks.append(
            {
                "type": "table",
                "title": "Hypotheses",
                "columns": ["Cause", "Confidence", "Evidence Refs"],
                "rows": hypothesis_rows,
            }
        )

    evidence_rows: list[list[str]] = []
    for item in evidence:
        if not isinstance(item, dict):
            continue
        ref = _coerce_str(item.get("ref"))
        source = _coerce_str(item.get("source"))
        snippet = _coerce_str(item.get("snippet"))
        if not (ref or snippet):
            continue
        evidence_rows.append([ref, _source_label(source), _truncate(snippet, 220)])
    if evidence_rows:
        blocks.append(
            {
                "type": "table",
                "title": "Evidence",
                "columns": ["Ref", "Source", "Snippet"],
                "rows": evidence_rows,
            }
        )

    owner_rows: list[list[str]] = []
    for item in owners:
        if not isinstance(item, dict):
            continue
        service_name = _coerce_str(item.get("service_name"))
        owner = _coerce_str(item.get("owner"))
        if not service_name or not owner or _RAW_OWNER_ID_PATTERN.fullmatch(owner):
            continue
        owner_rows.append([service_name, owner])
    if owner_rows:
        blocks.append(
            {
                "type": "table",
                "title": "Ownership",
                "columns": ["Service", "Owner"],
                "rows": owner_rows,
            }
        )

    escalation_rows: list[list[str]] = []
    for item in escalation:
        if not isinstance(item, dict):
            continue
        service_name = _coerce_str(item.get("service_name"))
        contacts = ", ".join(str(contact) for contact in _coerce_list(item.get("contacts")))
        if not service_name or not contacts.strip():
            continue
        escalation_rows.append([service_name, contacts])
    if escalation_rows:
        blocks.append(
            {
                "type": "table",
                "title": "Escalation",
                "columns": ["Service", "Contacts"],
                "rows": escalation_rows,
            }
        )

    if actions:
        blocks.append(
            {
                "type": "list",
                "title": "Recommended Actions",
                "items": actions[:5],
                "ordered": True,
            }
        )

    if report:
        blocks.append({"type": "markdown", "title": "Report", "content": report})

    return {
        "status_badge": {"value": status, "tone": _status_tone(status)},
        "status_reason": _status_reason(payload, status),
        "highlights": _highlights(summary, hypotheses, actions),
        "blocks": blocks,
    }


def enrich_structured_with_presentation(
    structured: dict[str, object] | None,
    *,
    fallback_summary: str | None = None,
) -> dict[str, object]:
    payload = dict(structured or {})
    if not _coerce_str(payload.get("summary")) and fallback_summary:
        payload["summary"] = fallback_summary
    payload["presentation"] = build_presentation(payload, fallback_summary=fallback_summary)
    return payload


def _status_value(payload: dict[str, object]) -> str:
    status = _coerce_str(payload.get("status"))
    if status:
        return status
    error = payload.get("error")
    if isinstance(error, dict):
        return _coerce_str(error.get("status")) or "error"
    return "complete"


def _status_tone(status: str) -> str:
    return {
        "complete": "success",
        "inconclusive": "warning",
        "not_found": "info",
        "error": "error",
    }.get(status, "info")


def _status_reason(payload: dict[str, object], status: str) -> str:
    if status == "complete":
        if _coerce_list(payload.get("evidence")):
            return "Sufficient evidence was found to produce a complete response."
        return "The response completed successfully."
    if status == "inconclusive":
        return "The investigation is inconclusive due to limited or missing evidence."
    if status == "not_found":
        return "The requested incident or service could not be found."
    error = payload.get("error")
    if isinstance(error, dict):
        detail = _first_non_empty_str(error.get("message"), error.get("next_action"))
        if detail:
            return detail
    return "The investigation failed due to a runtime or tool error."


def _highlights(
    summary: str,
    hypotheses: list[Any],
    actions: list[str],
) -> list[str]:
    out: list[str] = []
    if summary:
        out.append(_truncate(summary, 180))
    for item in hypotheses[:2]:
        if isinstance(item, dict):
            cause = _coerce_str(item.get("cause"))
            if cause:
                out.append(_truncate(cause, 140))
    out.extend(_truncate(action, 140) for action in actions[:2])
    deduped: list[str] = []
    seen: set[str] = set()
    for item in out:
        key = item.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped[:5]


def _coerce_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _coerce_str(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    return ""


def _first_non_empty_str(*values: object) -> str:
    for value in values:
        text = _coerce_str(value)
        if text:
            return text
    return ""


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    sentence_end = re.search(r"[.!?](?=\s|$)", text[max_len : max_len + 140])
    if sentence_end:
        end = max_len + sentence_end.end()
        return text[:end].strip()

    cut = text[:max_len]
    endings = list(re.finditer(r"[.!?](?=\s|$)", cut))
    if endings and endings[-1].end() >= int(max_len * 0.55):
        return cut[: endings[-1].end()].strip()

    boundary = cut.rfind(" ")
    if boundary > 0:
        return cut[:boundary].strip()
    return cut.strip()


def _source_label(source: str) -> str:
    if source == "db":
        return "Database"
    if source == "docs":
        return "Local document"
    if source == "session":
        return "Session memory"
    return source
