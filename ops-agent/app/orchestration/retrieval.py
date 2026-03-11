from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from app.tools.agent_tools import (
    get_escalation_contacts,
    get_incident_by_key,
    get_incident_evidence,
    get_incident_services,
    get_resolutions,
    get_service_dependencies,
    get_service_owner,
    get_similar_incidents,
    load_session_messages,
    search_docs,
)
from app.tools.contracts import make_no_data_response

ToolFn = Callable[..., dict[str, Any]]


class RetrievalExecutor:
    def __init__(self, tool_registry: dict[str, ToolFn] | None = None):
        self._tool_registry = tool_registry or self._default_registry()

    async def fan_out(
        self, tool_plan: list[dict[str, Any]]
    ) -> dict[str, list[dict[str, Any]]]:
        tasks = [self._run_plan_item(item) for item in tool_plan]
        results = await asyncio.gather(*tasks)

        merged: dict[str, list[dict[str, Any]]] = {
            "incident": [],
            "services": [],
            "evidence": [],
            "docs": [],
            "historical_incidents": [],
            "resolutions": [],
            "session_history": [],
        }

        for tool_name, payload in results:
            if not payload.get("ok", False):
                continue
            data = payload.get("data", [])
            if not isinstance(data, list):
                data = [data]

            if tool_name == "get_incident_by_key":
                merged["incident"].extend(data)
            elif tool_name in {
                "get_incident_services",
                "get_service_owner",
                "get_service_dependencies",
                "get_escalation_contacts",
            }:
                merged["services"].extend(data)
            elif tool_name == "get_incident_evidence":
                merged["evidence"].extend(data)
            elif tool_name == "search_docs":
                merged["docs"].extend(data)
            elif tool_name == "get_similar_incidents":
                merged["historical_incidents"].extend(data)
            elif tool_name == "get_resolutions":
                merged["resolutions"].extend(data)
            elif tool_name == "load_session_messages":
                merged["session_history"].extend(data)

        return merged

    async def _run_plan_item(self, item: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        tool_name = str(item.get("tool"))
        args = item.get("args", {})
        if not isinstance(args, dict):
            args = {}

        fn = self._tool_registry.get(tool_name)
        if fn is None:
            return tool_name, make_no_data_response(tool_name).model_dump()

        if any(str(v).startswith("$from_incident_services") for v in args.values()):
            return tool_name, make_no_data_response(tool_name).model_dump()

        result = fn(**args)
        return tool_name, result

    @staticmethod
    def _default_registry() -> dict[str, ToolFn]:
        return {
            "search_docs": search_docs,
            "load_session_messages": load_session_messages,
            "get_incident_by_key": get_incident_by_key,
            "get_incident_services": get_incident_services,
            "get_incident_evidence": get_incident_evidence,
            "get_service_owner": get_service_owner,
            "get_service_dependencies": get_service_dependencies,
            "get_similar_incidents": get_similar_incidents,
            "get_resolutions": get_resolutions,
            "get_escalation_contacts": get_escalation_contacts,
        }
