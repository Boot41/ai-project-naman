from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.tools.contracts import (
    make_error_response,
    make_no_data_response,
    make_success_response,
)

_INDEX_RELATIVE = Path("resources/index.json")
_CATEGORY_ALIASES = {
    "policy": "policies",
    "policies": "policies",
    "runbook": "runbooks",
    "runbooks": "runbooks",
    "postmortem": "postmortems",
    "postmortems": "postmortems",
    "architecture": "architecture",
}
_CATEGORY_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("policy", "policies"),
    ("runbook", "runbooks"),
    ("postmortem", "postmortems"),
    ("architecture", "architecture"),
)


def search_docs(
    query: str,
    *,
    top_k: int = 5,
    category: str | None = None,
    service: str | None = None,
    base_dir: Path | None = None,
) -> dict[str, Any]:
    source = "search_docs"
    try:
        query_tokens = _tokenize(query)
        if not query_tokens:
            return make_no_data_response(source).model_dump()

        repo_dir = base_dir or Path(__file__).resolve().parents[2]
        index_path = repo_dir / _INDEX_RELATIVE
        with index_path.open("r", encoding="utf-8") as f:
            index_payload = json.load(f)

        docs = index_payload.get("documents", [])
        filtered = _filter_docs(docs, category=category, service=service)
        ranked = _rank_docs(
            filtered, query_tokens=query_tokens, repo_dir=repo_dir, service=service
        )

        if not ranked:
            return make_no_data_response(source).model_dump()

        return make_success_response(source, ranked[:top_k]).model_dump()
    except Exception as exc:  # pragma: no cover - defensive envelope
        return make_error_response(source, "DOCS_SEARCH_FAILED", str(exc)).model_dump()


def _filter_docs(
    docs: list[dict[str, Any]],
    *,
    category: str | None,
    service: str | None,
) -> list[dict[str, Any]]:
    normalized_category = _normalize_category(category)
    out: list[dict[str, Any]] = []
    for doc in docs:
        doc_category = _normalize_category(str(doc.get("category", "")))
        if normalized_category and doc_category != normalized_category:
            continue
        if service and str(doc.get("service", "")).lower() != service.lower():
            continue
        out.append(doc)
    return out


def _normalize_category(category: str | None) -> str | None:
    if not category:
        return None
    lowered = category.strip().lower()
    if not lowered:
        return None
    direct = _CATEGORY_ALIASES.get(lowered)
    if direct:
        return direct

    # ADK planner may emit phrase-like categories, e.g. "incident response policy".
    for keyword, canonical in _CATEGORY_KEYWORDS:
        if keyword in lowered:
            return canonical

    return lowered


def _rank_docs(
    docs: list[dict[str, Any]],
    *,
    query_tokens: set[str],
    repo_dir: Path,
    service: str | None,
) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    for doc in docs:
        source_file = str(doc.get("file") or "").strip()
        if not source_file:
            continue

        content = _read_content(repo_dir, source_file)
        snippet = _build_snippet(content, query_tokens)

        score = _score_document(
            doc=doc, snippet=snippet, query_tokens=query_tokens, service=service
        )
        if score <= 0:
            continue

        ranked.append(
            {
                "doc_id": str(doc.get("id") or "unknown"),
                "category": str(doc.get("category") or "unknown"),
                "source_file": source_file,
                "service": doc.get("service"),
                "tags": doc.get("tags", []),
                "content_snippet": snippet,
                "score": round(score, 4),
            }
        )

    ranked.sort(key=lambda d: (-float(d["score"]), d["doc_id"]))
    return ranked


def _score_document(
    *,
    doc: dict[str, Any],
    snippet: str,
    query_tokens: set[str],
    service: str | None,
) -> float:
    title_tokens = _tokenize(str(doc.get("id") or ""))
    tag_tokens = _tokenize(" ".join(str(t) for t in doc.get("tags", [])))
    category_tokens = _tokenize(str(doc.get("category") or ""))
    snippet_tokens = _tokenize(snippet)

    score = 0.0
    score += 1.2 * len(query_tokens & title_tokens)
    score += 1.0 * len(query_tokens & tag_tokens)
    score += 0.6 * len(query_tokens & category_tokens)
    score += 0.8 * len(query_tokens & snippet_tokens)

    doc_service = str(doc.get("service") or "").lower()
    if service and doc_service and doc_service == service.lower():
        score += 2.0

    return score


def _read_content(repo_dir: Path, relative_path: str) -> str:
    file_path = repo_dir / relative_path
    if not file_path.exists():
        return ""
    return file_path.read_text(encoding="utf-8", errors="ignore")


def _build_snippet(content: str, query_tokens: set[str]) -> str:
    if not content:
        return "No content snippet available."

    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if not lines:
        return "No content snippet available."

    best_idx = _best_line_index(lines, query_tokens)
    if best_idx is None:
        return _truncate_sentence(lines[0], 280)

    # Return a short local window so the model gets actionable detail,
    # not just a heading token match.
    window = _snippet_window(lines, best_idx, max_lines=5)
    return _truncate_sentence(window, 560)


def _tokenize(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-zA-Z0-9\-]+", text.lower()) if token}


def _best_line_index(lines: list[str], query_tokens: set[str]) -> int | None:
    best_idx: int | None = None
    best_score = 0.0
    has_rca_query = bool({"root", "cause"} & query_tokens)
    has_action_query = bool(
        {"corrective", "action", "actions", "mitigation", "mitigations"} & query_tokens
    )

    for idx, line in enumerate(lines):
        line_tokens = _tokenize(line)
        overlap = len(query_tokens & line_tokens)
        if overlap == 0:
            continue

        score = float(overlap)
        lowered = line.lower()
        if "root cause" in lowered:
            score += 3.0
        if "mitigation" in lowered:
            score += 2.5
        if "corrective" in lowered or "actions" in lowered:
            score += 2.0

        if has_rca_query and ("root cause" in lowered):
            score += 2.0
        if has_action_query and (
            "mitigation" in lowered or "corrective" in lowered or "actions" in lowered
        ):
            score += 1.5

        if score > best_score:
            best_score = score
            best_idx = idx

    return best_idx


def _snippet_window(lines: list[str], center_idx: int, max_lines: int) -> str:
    start = max(0, center_idx - 1)
    end = min(len(lines), center_idx + max_lines)

    out: list[str] = []
    for idx in range(start, end):
        line = lines[idx]
        if idx > center_idx and line.startswith("#"):
            break
        out.append(line)

    return " ".join(out)


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
