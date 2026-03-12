# OpsCopilot File Flow

This document explains how a chat query travels across files, with a concrete example:

`Who owns payment-service and who are the escalation contacts?`

## End-to-End Flow (File Order)

1. `client/src/components/chat/Composer.tsx`
2. `client/src/pages/ChatPage.tsx`
3. `client/src/hooks/useChatState.ts` (`sendMessage`)
4. `client/src/lib/api.ts` (axios + auth header)
5. `client/vite.config.ts` (dev proxy `/api` -> `http://localhost:8020`)
6. `server/app/main.py` (FastAPI app + middleware stack)
7. `server/app/middleware/request_logging.py`
8. `server/app/middleware/error_handler.py`
9. `server/app/api/router.py` (routes under `/api/v1`)
10. `server/app/auth/deps.py` (`require_user` auth gate)
11. `server/app/api/routes/chat.py` (`POST /api/v1/chat/sessions/{session_id}/messages`)
12. `server/app/services/chat.py` (`create_chat_turn`)
13. `server/app/db/models.py` (persist user message)
14. `server/app/services/agent_client.py` (`investigate_ops_agent`)
15. `ops-agent/app/main.py` (`POST /v1/investigate`)
16. `ops-agent/app/schemas.py` (request schema)
17. `ops-agent/app/service.py`
18. `ops-agent/app/investigation_entry.py`
19. `ops-agent/app/agents/orchestrator_agent.py` (`run_investigation_via_root_agent`)
20. `ops-agent/app/agents/runtime.py` + `ops-agent/app/core/config.py`
21. `ops-agent/app/agents/orchestrator_agent.py` (orchestrator stage)
22. `ops-agent/app/agents/context_builder_agent.py`
23. `ops-agent/app/agents/incident_analysis_agent.py`
24. `ops-agent/app/agents/response_composer_agent.py`
25. `ops-agent/app/tools/agent_tools.py` (tool calls)
26. `ops-agent/app/tools/contracts.py` (tool envelopes)
27. `ops-agent/app/services/output_normalizer.py` (normalize output)
28. `ops-agent/app/services/enrichment.py` (owner/escalation backfill)
29. `ops-agent/app/services/output_normalizer.py` (final normalization)
30. `ops-agent/app/contracts/investigation_result.py` (result model)
31. `server/app/services/agent_client.py` (parse agent response)
32. `server/app/services/presentation.py` (presentation blocks)
33. `server/app/services/chat.py` (persist assistant message)
34. `server/app/db/models.py`
35. `server/app/api/routes/chat.py` (return response)
36. `client/src/hooks/useChatState.ts` (state update)
37. `client/src/components/chat/MessageList.tsx`
38. `client/src/components/chat/MessageBubble.tsx`

## Agent Sub-Flow (Inside `ops-agent/app/agents`)

1. `orchestrator_agent.py`
2. `context_builder_agent.py`
3. `incident_analysis_agent.py` (inside `LoopAgent`)
4. `response_composer_agent.py`

`root_agent` is declared in `orchestrator_agent.py` as:

- `SequentialAgent` with the 4 stages above
- `LoopAgent` wrapper around `IncidentAnalysisAgent`

## Ownership Query Notes

For ownership-style prompts (like this example), retrieval is expected to focus on:

- `get_service_owner(service_name="payment-service")`
- `get_escalation_contacts(service_name="payment-service")`

These run from:

- `ops-agent/app/tools/agent_tools.py`

If needed, enrichment may call them again to backfill missing owner/escalation details:

- `ops-agent/app/services/enrichment.py`

## Fallback Data Path

Tools are DB-first. If DB is unavailable, tools fall back to seed JSON under:

- `server/seed_data/services.json`
- `server/seed_data/users.json`
- `server/seed_data/escalation_contacts.json`
