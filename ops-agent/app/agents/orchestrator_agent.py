from __future__ import annotations

import logging
import os

from google.adk.agents import Agent
from google.adk.agents import LoopAgent
from google.adk.agents import SequentialAgent

from app.agents.context_builder_agent import context_builder_agent
from app.agents.incident_analysis_agent import incident_analysis_agent
from app.agents.orchestrator_planning import (
    build_orchestrator_plan,
    normalize_orchestrator_output,
)
from app.agents.response_composer_agent import response_composer_agent
from app.agents.runtime import build_stage_agent, run_json_stage_with_timeout
from app.contracts.incident_analysis import LoopRuntimePolicy
from app.contracts.orchestrator import OrchestratorInput, OrchestratorOutput
from app.core.config import get_settings
from app.tools.agent_tools import (
    get_escalation_contacts,
    get_investigation_bundle,
    get_incident_by_key,
    get_incident_services,
    get_resolutions,
    get_service_dependencies,
    get_service_owner,
    get_similar_incidents,
    load_session_messages,
    search_docs,
)

logger = logging.getLogger(__name__)
AGENT_NAME = "OpsCopilotOrchestratorAgent"
FLOW_AGENT_NAME = "OpsCopilotInvestigationFlow"
ANALYSIS_LOOP_AGENT_NAME = "IncidentAnalysisLoopAgent"
ORCHESTRATOR_STAGE_PROMPT = """
You are OpsCopilotOrchestratorAgent, the root OpsCopilot ADK entry agent.
Your job is to produce OrchestratorOutput JSON only.
Plan retrieval tools for incident investigation and route to context_builder.
Handoff contract:
- output must include `context_seed` with best-known `incident_key` and `service_name`
- tools should prefer single bundled retrieval first for stability
Do not return markdown, prose, or wrapper keys.
Do not return code fences (no ``` blocks).
Never say work is already done/processed.
Every user turn must produce a fresh plan.
Do not answer from general knowledge.
Flow: user query -> orchestrator -> parallel retrieval -> context builder -> analysis(loop) -> response composer.
Tool-call policy (strict):
- Default first retrieval call should be `get_investigation_bundle` with query/session_id and any known incident/service.
- For policy/runbook/postmortem/architecture questions, set `docs_category` to one of:
  `policies`, `runbooks`, `postmortems`, `architecture`.
- Ownership query ("who owns ... escalation contacts"): call `get_service_owner` then `get_escalation_contacts` only.
- Root-cause query for a known incident key: call `get_incident_by_key` then `get_resolutions` only.
- Comparison query ("compare ... similar incidents"): call tools in this exact order:
  1) `get_similar_incidents` with args `{"incident_key": "<primary_incident_key>"}`
  2) `get_incident_by_key` for the primary incident
  3) `get_resolutions` for the primary incident
  4) `get_incident_by_key` for top similar incident
  5) `get_resolutions` for top similar incident
  For this first call, do NOT send `limit` or extra args.
- Do NOT call `get_incident_evidence` for the above intents.
""".strip()

orchestrator_agent = build_stage_agent(
    name=AGENT_NAME,
    instruction=ORCHESTRATOR_STAGE_PROMPT,
    tools=[
        get_investigation_bundle,
        get_incident_by_key,
        get_incident_services,
        get_service_owner,
        get_service_dependencies,
        get_similar_incidents,
        get_resolutions,
        get_escalation_contacts,
        load_session_messages,
        search_docs,
    ],
)


def build_orchestrator_agent() -> Agent:
    return orchestrator_agent


async def orchestrate_with_adk_or_fallback(
    payload: OrchestratorInput,
) -> OrchestratorOutput:
    # Planning/normalization helpers are intentionally split to orchestrator_planning.py
    # so this module stays focused on ADK agent wiring and root runtime execution.
    try:
        adk_output = await run_json_stage_with_timeout(
            agent=orchestrator_agent,
            payload=payload,
            output_model=OrchestratorOutput,
            user_id=str(payload.user_id),
            timeout_seconds=45,
        )
        return normalize_orchestrator_output(payload, adk_output)
    except Exception:
        return build_orchestrator_plan(payload)


settings = get_settings()
if settings.google_api_key.strip():
    os.environ["GOOGLE_API_KEY"] = settings.google_api_key.strip()

# Graph-visible ADK flow for ADK Web: stage agents are first-class sub-agents.
analysis_loop_agent = LoopAgent(
    name=ANALYSIS_LOOP_AGENT_NAME,
    description="Loop analysis stage up to policy max iterations.",
    sub_agents=[incident_analysis_agent],
    max_iterations=LoopRuntimePolicy().max_iterations,
)

root_agent = SequentialAgent(
    name=FLOW_AGENT_NAME,
    description="Sequential OpsCopilot multi-agent flow graph.",
    sub_agents=[
        orchestrator_agent,
        context_builder_agent,
        analysis_loop_agent,
        response_composer_agent,
    ],
)


def get_configured_entry_agent() -> Agent:
    return root_agent
