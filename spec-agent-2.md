# Spec Agent 2: ContextBuilderAgent

## Purpose

Converts retrieved tool outputs into compact, grounded context for analysis.

## Runtime Mapping

- File: `ops-agent/app/agents/context_builder_agent.py`
- Stage function: `context_builder_with_adk_or_fallback(...)`

## Input Contract

`ContextBuilderInput` from `ops-agent/app/contracts/context_builder.py`.

## Output Contract

`ContextBuilderOutput` from `ops-agent/app/contracts/context_builder.py`.

## Behavior Rules

- JSON only
- preserve evidence references
- compress content for downstream reasoning
- include `open_questions` when data is missing
- set `status=not_found` when incident scope requires incident row but none exists

## Acceptance Criteria

- Returns schema-valid context payload
- Includes concise `context_content`
- Explicitly marks insufficient information gaps
