from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4


@dataclass
class InMemoryPersistenceGateway:
    messages: list[dict[str, Any]] = field(default_factory=list)
    evidence_rows: list[dict[str, Any]] = field(default_factory=list)
    sessions_last_activity: dict[str, str] = field(default_factory=dict)

    def save_assistant_message(
        self,
        *,
        session_id: UUID,
        content_text: str,
        structured_json: dict[str, Any],
    ) -> str:
        message_id = str(uuid4())
        self.messages.append(
            {
                "id": message_id,
                "session_id": str(session_id),
                "role": "assistant",
                "content_text": content_text,
                "structured_json": structured_json,
            }
        )
        return message_id

    def save_investigation_evidence(
        self,
        *,
        session_id: UUID,
        message_id: str,
        evidence_refs: list[str],
    ) -> None:
        for ref in evidence_refs:
            self.evidence_rows.append(
                {
                    "session_id": str(session_id),
                    "message_id": message_id,
                    "evidence_type": "analysis_ref",
                    "evidence_ref": ref,
                }
            )

    def update_session_last_activity(self, *, session_id: UUID) -> None:
        self.sessions_last_activity[str(session_id)] = datetime.now(tz=UTC).isoformat()
