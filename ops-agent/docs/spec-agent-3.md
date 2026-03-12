# Spec Agent 3: IncidentAnalysisAgent

## Purpose

Performs evidence-based incident reasoning and decides stop/continue/inconclusive.

## Runtime Mapping

- File: `ops-agent/app/agents/incident_analysis_agent.py`
- Stage function: `analysis_with_adk_or_fallback(...)`
- Loop control: `ops-agent/app/investigation_flow.py`

## Input Contract

`IncidentAnalysisInput` from `ops-agent/app/contracts/incident_analysis.py`.

## Output Contract

`IncidentAnalysisOutput` from `ops-agent/app/contracts/incident_analysis.py`.

## Loop Rules

- Runtime loop is managed by `run_investigation_pipeline(...)`
- May request more data based on `missing_information`
- Stops on `analysis_decision != continue` or policy limit

## Reasoning Constraints

- hypotheses must be evidence-backed
- no unsupported causal claims
- when unresolved, return inconclusive and explicit missing data

## Acceptance Criteria

- Returns valid analysis JSON
- Honors loop decision fields
- Emits inconclusive state when evidence is insufficient
