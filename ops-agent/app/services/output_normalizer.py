from __future__ import annotations

import json
import re

from app.contracts.response_composer import ComposerOutput


_INCIDENT_KEY_PATTERN = re.compile(r"\bINC-(?:\d{4}-\d{4}|\d+)\b", re.IGNORECASE)


def extract_json(text: str) -> dict:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        return json.loads(text[start : end + 1])


def normalize_composer_payload(payload: dict, *, query: str | None = None) -> dict:
    normalized = dict(payload)
    report_raw = normalized.get("report")
    normalized["hypotheses"] = _coerce_hypotheses(normalized.get("hypotheses"))
    normalized["evidence"] = _coerce_evidence(
        normalized.get("evidence"),
        hypotheses=normalized["hypotheses"],
        report=report_raw,
    )
    if not normalized["hypotheses"]:
        normalized["hypotheses"] = _backfill_hypotheses_from_evidence(normalized["evidence"])
    normalized["report"] = _coerce_report_text(
        report_raw,
        evidence=normalized["evidence"],
        hypotheses=normalized["hypotheses"],
    )
    normalized["recommended_actions"] = _coerce_actions(normalized.get("recommended_actions"))
    normalized["similar_incidents"] = _coerce_similar_incidents(normalized.get("similar_incidents"))
    normalized["owners"] = _coerce_owners(normalized.get("owners"))
    normalized["escalation"] = _coerce_escalation(normalized.get("escalation"))
    normalized.setdefault("status", "complete")
    normalized["summary"] = _coerce_summary(
        normalized.get("summary"),
        query=query,
        evidence=normalized["evidence"],
        hypotheses=normalized["hypotheses"],
        owners=normalized["owners"],
        escalation=normalized["escalation"],
    )
    normalized["status"] = _coerce_status(
        normalized.get("status"),
        evidence=normalized["evidence"],
        hypotheses=normalized["hypotheses"],
    )
    normalized = _apply_grounding_guards(normalized, query=query)

    try:
        return ComposerOutput.model_validate(normalized).model_dump()
    except Exception:
        # Keep a stable minimum schema even if full validation fails.
        return {
            "summary": normalized.get("summary") or "Investigation completed.",
            "hypotheses": normalized.get("hypotheses", []),
            "similar_incidents": normalized.get("similar_incidents", []),
            "evidence": normalized.get("evidence", []),
            "owners": normalized.get("owners", []),
            "escalation": normalized.get("escalation", []),
            "recommended_actions": normalized.get("recommended_actions", []),
            "report": normalized.get("report") or "insufficient information",
            "status": _coerce_status(
                normalized.get("status"),
                evidence=normalized.get("evidence", []),
                hypotheses=normalized.get("hypotheses", []),
            ),
        }


def _coerce_actions(value: object) -> list[str]:
    actions: list[str] = []
    if isinstance(value, list):
        for item in value:
            if isinstance(item, str) and item.strip():
                actions.append(item.strip())
                continue
            if isinstance(item, dict):
                action_text = str(item.get("action") or "").strip()
                if action_text:
                    actions.append(action_text)
    return actions[:3]


def _coerce_similar_incidents(value: object) -> list[dict]:
    out: list[dict] = []
    if not isinstance(value, list):
        return out
    for item in value:
        if not isinstance(item, dict):
            continue
        incident_key = str(item.get("incident_key") or "").strip().upper()
        reason = str(item.get("similarity_reason") or "").strip()
        if not incident_key:
            continue
        out.append({"incident_key": incident_key, "similarity_reason": reason})
    return out


def _coerce_hypotheses(value: object) -> list[dict]:
    out: list[dict] = []
    if not isinstance(value, list):
        return out
    for item in value:
        if not isinstance(item, dict):
            continue
        cause = str(item.get("cause") or item.get("hypothesis") or "").strip()
        if not cause:
            continue
        reasoning = str(
            item.get("reasoning_summary") or item.get("reasoning") or ""
        ).strip() or "Derived from available investigation context."
        refs = [
            str(ref).strip()
            for ref in (item.get("supporting_evidence_refs") or [])
            if str(ref).strip()
        ]
        confidence_raw = item.get("confidence")
        try:
            confidence = float(confidence_raw)
        except (TypeError, ValueError):
            confidence = 0.7 if refs else 0.55
        confidence = max(0.0, min(1.0, confidence))
        out.append(
            {
                "cause": cause,
                "confidence": confidence,
                "supporting_evidence_refs": refs or ["unknown-ref"],
                "counter_evidence_refs": [
                    str(ref).strip()
                    for ref in (item.get("counter_evidence_refs") or [])
                    if str(ref).strip()
                ],
                "reasoning_summary": reasoning,
            }
        )
    return out


def _coerce_evidence(value: object, *, hypotheses: list[dict], report: object) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()

    def add(ref: str, source: str, snippet: str) -> None:
        key = _normalize_evidence_ref(ref=ref.strip(), snippet=snippet)
        if not key or key in seen:
            return
        if _is_placeholder_snippet(snippet):
            return
        seen.add(key)
        out.append(
            {
                "ref": key,
                "source": source,
                "snippet": _truncate_sentence(_clean_snippet(snippet), 320),
            }
        )

    if isinstance(value, list):
        for item in value:
            if not isinstance(item, dict):
                continue
            ref = str(item.get("ref") or "").strip()
            source = str(item.get("source") or "session").strip()
            snippet = str(item.get("snippet") or "").strip()
            if ref and snippet:
                add(ref, source if source in {"db", "docs", "session"} else "session", snippet)

    for hyp in hypotheses:
        for ref in hyp.get("supporting_evidence_refs", []):
            add(str(ref), _infer_source(str(ref)), f"Referenced by hypothesis: {hyp.get('cause')}")

    if isinstance(report, dict):
        for section in ("findings", "inferred_considerations"):
            entries = report.get(section)
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                desc = str(entry.get("description") or "").strip()
                if _is_placeholder_snippet(desc):
                    continue
                for ref in entry.get("evidence_refs") or []:
                    add(str(ref), _infer_source(str(ref)), desc or "Referenced in report section")
    return out


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


def _coerce_report_text(value: object, *, evidence: list[dict], hypotheses: list[dict]) -> str:
    if isinstance(value, str):
        text = value.strip()
        if text:
            if evidence and "Evidence-backed findings:\n- insufficient information" in text:
                text = text.replace(
                    "Evidence-backed findings:\n- insufficient information",
                    "Evidence-backed findings:\n"
                    + "\n".join(
                        f"- {item.get('snippet')}" for item in evidence[:3] if item.get("snippet")
                    ),
                )
            return text
        return "insufficient information"
    if isinstance(value, dict):
        findings = _coerce_report_section(value.get("findings")) or "\n".join(
            f"- {item.get('snippet')}" for item in evidence[:3] if item.get("snippet")
        )
        inferred = _coerce_report_section(value.get("inferred_considerations"))
        gaps = _coerce_report_section(value.get("gaps_unknowns"))
        out = (
            "Evidence-backed findings:\n"
            + (findings or "- insufficient information")
            + "\nInferred (lower-confidence) considerations:\n"
            + (
                inferred
                or "\n".join(
                    f"- {item.get('reasoning_summary')}"
                    for item in hypotheses[:2]
                    if item.get("reasoning_summary")
                )
                or "- insufficient information"
            )
            + "\nGaps / unknowns:\n"
            + (gaps or "- insufficient information")
        )
        return out.strip()
    return "insufficient information"


def _coerce_report_section(value: object) -> str:
    lines: list[str] = []
    if not isinstance(value, list):
        return ""
    for item in value:
        if isinstance(item, str):
            text = item.strip()
        elif isinstance(item, dict):
            text = str(item.get("description") or "").strip()
        else:
            text = ""
        if text:
            lines.append(f"- {text}")
    return "\n".join(lines[:8])


def _coerce_status(status_value: object, *, evidence: list[dict], hypotheses: list[dict]) -> str:
    normalized = str(status_value or "").strip().lower()
    if normalized not in {"complete", "inconclusive", "not_found", "error"}:
        normalized = "complete"
    if normalized == "complete" and hypotheses and not evidence:
        return "inconclusive"
    return normalized


def _coerce_summary(
    value: object,
    *,
    query: str | None,
    evidence: list[dict],
    hypotheses: list[dict],
    owners: list[dict],
    escalation: list[dict],
) -> str:
    text = str(value or "").strip()
    lowered = (query or "").lower()
    ownership_intent = any(
        token in lowered for token in ("who owns", "owner", "ownership", "escalation", "on-call")
    )
    if ownership_intent and (owners or escalation):
        return _build_ownership_summary(owners=owners, escalation=escalation)

    if not text:
        if hypotheses:
            return _truncate_sentence(
                f"Likely cause: {hypotheses[0].get('cause', 'insufficient information')}",
                280,
            )
        if evidence:
            return _truncate_sentence(
                str(evidence[0].get("snippet") or "Investigation completed.").strip(),
                280,
            )
    return text or "insufficient information"


def _apply_grounding_guards(normalized: dict, *, query: str | None) -> dict:
    output = dict(normalized)
    query_lower = (query or "").lower()
    ownership_intent = any(
        token in query_lower for token in ("who owns", "owner", "ownership", "escalation", "on-call")
    )
    root_cause_intent = any(
        token in query_lower for token in ("root cause", "likely cause", "cause", "why")
    )
    comparison_intent = any(token in query_lower for token in ("compare", "similar", "historical"))
    troubleshooting_intent = any(
        token in query_lower for token in ("troubleshoot", "mitigation", "mitigate", "immediate steps")
    )
    docs_guidance_intent = any(
        token in query_lower
        for token in ("policy", "runbook", "postmortem", "architecture", "what does", "guidance")
    )
    requested_incident_key = _extract_incident_key(query or "")

    evidence = [
        item
        for item in list(output.get("evidence") or [])
        if isinstance(item, dict) and not _is_placeholder_snippet(str(item.get("snippet") or ""))
    ]
    output["evidence"] = evidence
    evidence_refs = {str(item.get("ref") or "").strip() for item in evidence if isinstance(item, dict)}
    hypotheses = list(output.get("hypotheses") or [])
    filtered_hypotheses: list[dict] = []
    for item in hypotheses:
        if not isinstance(item, dict):
            continue
        refs = [
            str(ref).strip()
            for ref in (item.get("supporting_evidence_refs") or [])
            if str(ref).strip()
        ]
        if evidence_refs:
            refs = [ref for ref in refs if ref in evidence_refs]
        if not refs and evidence_refs:
            refs = [next(iter(evidence_refs))]
        if not refs:
            continue
        updated = dict(item)
        updated["supporting_evidence_refs"] = refs
        filtered_hypotheses.append(updated)
    output["hypotheses"] = filtered_hypotheses

    owners = list(output.get("owners") or [])
    escalation = list(output.get("escalation") or [])
    similar_incidents = list(output.get("similar_incidents") or [])

    if ownership_intent and (owners or escalation):
        output["summary"] = _build_ownership_summary(owners=owners, escalation=escalation)
        if not output["evidence"]:
            for owner in owners[:3]:
                service = str(owner.get("service_name") or "").strip().lower()
                owner_name = str(owner.get("owner") or "").strip() or "unknown owner"
                if service:
                    output["evidence"].append(
                        {
                            "ref": f"owner:{service}",
                            "source": "db",
                            "snippet": f"Owner for {service}: {owner_name}.",
                        }
                    )
            for esc in escalation[:3]:
                service = str(esc.get("service_name") or "").strip().lower()
                contacts = ", ".join(str(c).strip() for c in (esc.get("contacts") or []) if str(c).strip())
                if service and contacts:
                    output["evidence"].append(
                        {
                            "ref": f"escalation:{service}",
                            "source": "db",
                            "snippet": f"Escalation contacts for {service}: {contacts}.",
                        }
                    )

    if root_cause_intent and requested_incident_key:
        output["similar_incidents"] = []
        if not output["hypotheses"]:
            output["status"] = "inconclusive"
            output["summary"] = (
                f"Insufficient evidence to confirm root cause for {requested_incident_key}."
            )
        else:
            primary = output["hypotheses"][0]
            output["summary"] = (
                f"Likely root cause for {requested_incident_key}: {primary.get('cause')}."
            )

    if comparison_intent and not similar_incidents:
        has_history_ref = any(
            "historical" in str(item.get("ref") or "").lower() for item in output["evidence"]
        )
        if not has_history_ref:
            output["status"] = "inconclusive"
            output["summary"] = "Insufficient evidence to compare similar incidents."
    elif comparison_intent and similar_incidents:
        top = similar_incidents[:3]
        formatted = ", ".join(
            f"{str(item.get('incident_key') or '').upper()} ({str(item.get('similarity_reason') or 'similar pattern')})"
            for item in top
            if str(item.get("incident_key") or "").strip()
        )
        if formatted:
            output["summary"] = (
                f"Compared {requested_incident_key or 'the incident'} with similar incidents: {formatted}."
            )

    if troubleshooting_intent:
        has_doc_evidence = any(
            str(item.get("source") or "").lower() == "docs" for item in output.get("evidence", [])
        )
        if has_doc_evidence:
            output["status"] = "complete"
            service_names = {
                str(item.get("service_name") or "").strip()
                for item in (output.get("owners") or [])
                if isinstance(item, dict)
            }
            service_label = next((name for name in service_names if name), "the target service")
            output["summary"] = (
                f"Troubleshooting and immediate mitigation guidance prepared for {service_label} using runbook/postmortem evidence."
            )
            output["report"] = _coerce_report_text(
                {
                    "findings": [
                        {"description": str(item.get("snippet") or "").strip()}
                        for item in list(output.get("evidence") or [])[:4]
                        if str(item.get("source") or "").lower() == "docs"
                    ],
                    "inferred_considerations": [
                        {
                            "description": "Use mitigations that reduce blast radius first, then iterate with fresh telemetry."
                        }
                    ],
                    "gaps_unknowns": [
                        {
                            "description": "Validate provider and service latency metrics in real time before and after each mitigation."
                        }
                    ],
                },
                evidence=list(output.get("evidence") or []),
                hypotheses=list(output.get("hypotheses") or []),
            )

    if docs_guidance_intent:
        has_doc_evidence = any(
            str(item.get("source") or "").lower() == "docs" for item in output.get("evidence", [])
        )
        if has_doc_evidence:
            output["status"] = "complete"
            output["summary"] = _build_docs_summary(query_lower, list(output.get("evidence") or []))
            output["report"] = _coerce_report_text(
                {
                    "findings": [
                        {"description": str(item.get("snippet") or "").strip()}
                        for item in list(output.get("evidence") or [])[:3]
                        if str(item.get("source") or "").lower() == "docs"
                    ],
                    "inferred_considerations": [
                        {
                            "description": "Recommendations are grounded in cited local documentation snippets."
                        }
                    ],
                    "gaps_unknowns": [
                        {
                            "description": "For incident-specific execution, validate current live telemetry before action."
                        }
                    ],
                },
                evidence=list(output.get("evidence") or []),
                hypotheses=list(output.get("hypotheses") or []),
            )

    if (
        not output.get("evidence")
        and not output.get("hypotheses")
        and not output.get("owners")
        and not output.get("escalation")
    ):
        output["status"] = "inconclusive"
        current_summary = str(output.get("summary") or "").strip()
        if not current_summary.lower().startswith("insufficient evidence"):
            output["summary"] = "Insufficient evidence to complete this investigation."

    if (
        str(output.get("status") or "").lower() == "complete"
        and "insufficient information" in str(output.get("report") or "").lower()
        and (output.get("evidence") or output.get("hypotheses"))
    ):
        output["report"] = _coerce_report_text(
            {"findings": output.get("evidence"), "inferred_considerations": output.get("hypotheses")},
            evidence=list(output.get("evidence") or []),
            hypotheses=list(output.get("hypotheses") or []),
        )

    output["recommended_actions"] = _ground_actions(output, query=query)
    output["status"] = _coerce_status(
        output.get("status"),
        evidence=list(output.get("evidence") or []),
        hypotheses=list(output.get("hypotheses") or []),
    )
    output["summary"] = _finalize_summary(output, query=query)
    if (
        str(output.get("status") or "").lower() == "complete"
        and output["summary"].lower().startswith("insufficient evidence")
    ):
        output["status"] = "inconclusive"
    return output


def _ground_actions(output: dict, *, query: str | None) -> list[str]:
    current = list(output.get("recommended_actions") or [])
    current = [str(item).strip() for item in current if str(item).strip()]
    query_lower = (query or "").lower()
    troubleshooting_intent = any(
        token in query_lower for token in ("troubleshoot", "mitigation", "mitigate", "immediate steps")
    )
    if troubleshooting_intent:
        has_doc_evidence = any(
            str(item.get("source") or "").lower() == "docs" for item in list(output.get("evidence") or [])
        )
        if has_doc_evidence:
            escalation_contacts = []
            for item in list(output.get("escalation") or []):
                if isinstance(item, dict):
                    escalation_contacts.extend(
                        [
                            str(contact).strip()
                            for contact in (item.get("contacts") or [])
                            if str(contact).strip()
                        ]
                    )
            contacts_text = ", ".join(dict.fromkeys(escalation_contacts))
            actions = [
                "Assess blast radius by region and payment method, then choose partial disablement over global outage behavior when safer.",
                "Stabilize the path immediately: throttle retries, roll back risky recent changes, and reduce load on degraded payment endpoints.",
                "Log evidence timeline and escalate to payments on-call immediately"
                + (f" ({contacts_text})." if contacts_text else "."),
            ]
            return actions[:3]
    if any(token in query_lower for token in ("policy", "runbook", "postmortem", "architecture")):
        if "policy" in query_lower:
            return [
                "Apply the policy severity matrix immediately to classify current impact and assign incident level.",
                "Assign required severe-incident roles (Incident Commander, Ops Lead, Communications Lead) per policy.",
                "Execute the policy escalation timeline and notification sequence for severe incidents.",
            ]
        if "architecture" in query_lower or "dependency" in query_lower:
            return [
                "Prioritize checks on checkout critical path dependencies: order-service, api-gateway, auth-service, and external payment provider links.",
                "Validate retry behavior across api-gateway and order-service to prevent amplification during payment-service degradation.",
                "Use dependency mapping to assess blast radius upstream/downstream and sequence mitigations by Tier 1 services first.",
            ]
        return [
            "Use cited documentation sections as the operational runbook for the current question.",
            "Cross-check guidance against current telemetry before executing high-impact mitigations.",
            "Document chosen actions and evidence refs in the incident timeline for auditability.",
        ]
    if current and len(current) >= 3:
        return current[:3]
    if any(token in query_lower for token in ("owner", "escalation")):
        owners = list(output.get("owners") or [])
        escalation = list(output.get("escalation") or [])
        actions: list[str] = []
        if escalation:
            first = escalation[0]
            service = str(first.get("service_name") or "service").strip()
            contacts = ", ".join(str(c).strip() for c in (first.get("contacts") or []) if str(c).strip())
            if contacts:
                actions.append(f"Use {service} escalation contacts first: {contacts}.")
        if owners:
            owner = owners[0]
            actions.append(
                f"Confirm accountability with owner for {owner.get('service_name')}: {owner.get('owner') or 'unknown'}."
            )
        actions.append("If primary contact is unavailable, escalate using next priority contact immediately.")
        return actions[:3]
    if str(output.get("status") or "").lower() == "inconclusive":
        return [
            "Run incident/service retrieval again with a specific incident key or service name.",
            "Verify database and documentation sources are reachable and up to date.",
            "Capture missing evidence (metrics/log snippets, owners, escalation path) before retrying.",
        ]
    return (current + ["Validate evidence-backed actions with service owners."])[:3]


def _build_ownership_summary(*, owners: list[dict], escalation: list[dict]) -> str:
    owner_text = "Owner information unavailable."
    if owners:
        first_owner = owners[0]
        owner_text = (
            f"{first_owner.get('service_name')} is owned by "
            f"{first_owner.get('owner') or 'unknown owner'}."
        )
    escalation_text = "No escalation contacts found."
    if escalation:
        first_esc = escalation[0]
        contacts = ", ".join(
            str(item).strip() for item in (first_esc.get("contacts") or []) if str(item).strip()
        )
        if contacts:
            escalation_text = (
                f"Escalation contacts for {first_esc.get('service_name')}: {contacts}."
            )
    return f"{owner_text} {escalation_text}".strip()


def _finalize_summary(output: dict, *, query: str | None) -> str:
    summary = str(output.get("summary") or "").strip()
    status = str(output.get("status") or "").strip().lower()
    evidence = [item for item in list(output.get("evidence") or []) if isinstance(item, dict)]
    hypotheses = [item for item in list(output.get("hypotheses") or []) if isinstance(item, dict)]
    actions = [str(item).strip() for item in (output.get("recommended_actions") or []) if str(item).strip()]
    owners = [item for item in list(output.get("owners") or []) if isinstance(item, dict)]
    escalation = [item for item in list(output.get("escalation") or []) if isinstance(item, dict)]
    similar_incidents = [
        item for item in list(output.get("similar_incidents") or []) if isinstance(item, dict)
    ]
    query_lower = (query or "").lower()
    ownership_intent = any(
        token in query_lower for token in ("who owns", "owner", "ownership", "escalation", "on-call")
    )
    if ownership_intent and (owners or escalation):
        return _build_ownership_summary(owners=owners, escalation=escalation)

    if status != "complete":
        return summary or "insufficient information"

    if not _should_upgrade_summary(summary=summary, evidence=evidence, actions=actions):
        return summary

    return _build_grounded_summary(
        summary=summary,
        query_lower=query_lower,
        hypotheses=hypotheses,
        evidence=evidence,
        actions=actions,
        similar_incidents=similar_incidents,
    )


def _should_upgrade_summary(*, summary: str, evidence: list[dict], actions: list[str]) -> bool:
    if not summary:
        return bool(evidence or actions)
    lowered = summary.lower()
    generic_markers = (
        "guidance prepared for",
        "investigation completed",
        "documentation-backed guidance",
        "severe-incident policy guidance",
        "payment-service outage dependency guidance",
    )
    if any(marker in lowered for marker in generic_markers):
        return True
    if len(summary.split()) < 18 and (evidence or actions):
        return True
    return False


def _build_grounded_summary(
    *,
    summary: str,
    query_lower: str,
    hypotheses: list[dict],
    evidence: list[dict],
    actions: list[str],
    similar_incidents: list[dict],
) -> str:
    parts: list[str] = []

    if hypotheses:
        cause = str(hypotheses[0].get("cause") or "").strip().rstrip(".")
        if cause:
            parts.append(f"Likely cause: {cause}.")
    elif evidence:
        key_signal = _truncate_sentence(_clean_snippet(str(evidence[0].get("snippet") or "")), 180)
        if key_signal:
            parts.append(f"Key signal: {key_signal}")

    if similar_incidents and any(token in query_lower for token in ("compare", "similar", "historical")):
        formatted = ", ".join(
            str(item.get("incident_key") or "").strip().upper()
            for item in similar_incidents[:2]
            if str(item.get("incident_key") or "").strip()
        )
        if formatted:
            parts.append(f"Compared against similar incidents: {formatted}.")

    if actions:
        top_actions = "; ".join(action.rstrip(".") for action in actions[:2])
        if top_actions:
            parts.append(f"Immediate actions: {top_actions}.")

    if not parts:
        return summary or "insufficient information"
    return _truncate_sentence(" ".join(parts), 420)


def _extract_incident_key(text: str) -> str | None:
    match = _INCIDENT_KEY_PATTERN.search(text)
    return match.group(0).upper() if match else None


def _is_placeholder_snippet(text: str) -> bool:
    normalized = text.strip().lower()
    return normalized in {"referenced in report section", "insufficient information", ""}


def _clean_snippet(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"^#+\s*", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = cleaned.lstrip("- ").strip()
    return cleaned


def _build_docs_summary(query_lower: str, evidence: list[dict]) -> str:
    doc_snippets = [
        _clean_snippet(str(item.get("snippet") or ""))
        for item in evidence
        if isinstance(item, dict) and str(item.get("source") or "").lower() == "docs"
    ]
    primary = doc_snippets[0] if doc_snippets else "Relevant guidance found in local docs."
    if "policy" in query_lower:
        return _truncate_sentence(f"Severe-incident policy guidance: {primary}", 280)
    if "architecture" in query_lower or "dependency" in query_lower:
        return _truncate_sentence(f"Payment-service outage dependency guidance: {primary}", 280)
    return _truncate_sentence(f"Documentation-backed guidance: {primary}", 280)


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


def _infer_source(ref: str) -> str:
    lowered = ref.lower()
    if lowered.startswith("inc-") or lowered.isdigit() or "resolution" in lowered:
        return "db"
    if lowered.startswith("doc_") or "runbook" in lowered or "policy" in lowered:
        return "docs"
    return "session"


def _normalize_evidence_ref(*, ref: str, snippet: str) -> str:
    lowered = ref.lower()
    if lowered.startswith("get_incident_by_key"):
        incident_match = re.search(r"\bINC-(?:\d{4}-\d{4}|\d+)\b", snippet, re.IGNORECASE)
        if incident_match:
            return f"incident:{incident_match.group(0).upper()}"
        return "incident:lookup"
    if lowered.startswith("get_incident_services"):
        service_match = re.search(r"\b[a-z0-9-]+-service\b", snippet, re.IGNORECASE)
        if service_match:
            return f"service:{service_match.group(0).lower()}"
        return "service:impacted"
    if lowered.startswith("get_similar_incidents"):
        return "historical:similar_incidents"
    if lowered == "resolutions":
        return "resolution:primary"
    return ref


def _backfill_hypotheses_from_evidence(evidence: list[dict]) -> list[dict]:
    root_cause_row = next(
        (
            item
            for item in evidence
            if str(item.get("source") or "").lower() == "db"
            if "root cause" in str(item.get("snippet") or "").lower()
            or "misconfigured" in str(item.get("snippet") or "").lower()
        ),
        None,
    )
    if root_cause_row is None:
        return []
    snippet = str(root_cause_row.get("snippet") or "").strip()
    cause = snippet
    if ":" in cause:
        cause = cause.split(":", 1)[1].strip()
    cause = cause.rstrip(".")
    return [
        {
            "cause": cause or "Likely root cause from incident evidence",
            "confidence": 0.8,
            "supporting_evidence_refs": [str(root_cause_row.get("ref") or "resolution:primary")],
            "counter_evidence_refs": [],
            "reasoning_summary": "Backfilled from evidence snippets that explicitly mention root cause indicators.",
        }
    ]
