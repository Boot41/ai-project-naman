# Local Document Specification: OpsCopilot Incident Investigation Docs

## Purpose
This specification defines the required structure, style, and quality checks for the OpsCopilot operational documentation pack stored in `download/`. The goal is to ensure each document is directly usable by operations engineers during active incidents and post-incident review.

## Output Location And Filenames
All files must be written to:
`/home/dell/Desktop/week-4/ai-project/download/`

Required files:
1. `api-gateway-runbook.txt`
2. `payment-service-runbook.txt`
3. `auth-service-runbook.txt`
4. `search-service-runbook.txt`
5. `incident-payment-latency.txt`
6. `incident-search-outage.txt`
7. `system-overview.txt`
8. `service-dependencies.txt`
9. `incident-response-policy.txt`

Additional control file:
10. `local-document-spec.md`

## Format Contract
- All operational documents are plain text `.txt` files.
- ASCII only.
- No external links are required for usability.
- Documents must be readable as standalone references.
- Use clear headings and short paragraphs suitable for on-call use.
- Prefer role-based contacts (for example, `Primary On-Call SRE`) rather than personal identifiers.

## Section Requirements
Runbooks must include these sections exactly:
- Service Description
- Common Failure Modes
- Important Metrics
- Investigation Steps
- Recovery Steps
- Escalation Contacts

Postmortems must include these sections exactly:
- Incident Summary
- Timeline
- Root Cause
- Impact
- Mitigation
- Lessons Learned

Architecture documents must cover:
- Architecture explanation
- Service relationships
- Dependency chains

Policy document must cover:
- Incident severity definitions
- Response process
- Escalation guidelines

## Content And Consistency Rules
- Use the same service catalog everywhere:
  - `api-gateway`, `auth-service`, `payment-service`, `user-service`, `order-service`, `inventory-service`, `notification-service`, `search-service`, `analytics-service`.
- Keep dependency chains consistent between architecture docs and runbooks.
- Ensure postmortem failure patterns are recognizable in runbook failure modes and metrics.
- Keep language action-oriented: what to check, what evidence to gather, what to do next.

## Length And Quality Gates
- Each required `.txt` file should be approximately 800–1000 words.
- Each file should provide concrete technical detail, not generic process filler.
- Include realistic metrics, alert symptoms, and recovery paths.

## Validation Checklist
1. Verify all 10 files exist in `download/`.
2. Run `wc -w download/*.txt` and confirm each `.txt` file is near target (800–1000 words).
3. Confirm required section headings are present using `rg`.
4. Confirm service naming and dependency narrative consistency across files.
5. Confirm each runbook contains actionable escalation triggers.

## Extended Content Revision (v2)

This revision expands every operational text document with additional investigation, containment, and recovery data to support richer agent retrieval and operator workflows.

### Metadata Update Rules
- Each document now carries an extended narrative section labeled as supplemental operational data.
- The metadata registry must track:
  - document id
  - category
  - source path
  - service scope (if applicable)
  - revision tag
  - retrieval tags
- Word-count targets for extended docs are now significantly above the original baseline and should remain stable across future updates.

### Retrieval Optimization Notes
- Prefer top-level category filtering before full-text ranking.
- Route by service tag when query explicitly names a service.
- Route by incident phase tag (`detect`, `triage`, `mitigate`, `recover`, `review`) when service is unknown.
- Use architecture and policy documents as fallback context for cross-service or process-heavy queries.

### Quality Controls
- Every extended section must remain actionable and evidence-oriented.
- Avoid purely repetitive wording; new sections should add decision support value.
- Keep escalation and rollback guidance explicit where operational risk is high.


## Metadata And Length Assurance Update (v3)

### Length Assurance
- Every primary text document under `download/` must remain above the doubled baseline established from initial v1 generation.
- Validation should be performed with `wc -w` after each major update cycle.

### Metadata Enrichment Recommendations
- Include service scope where applicable.
- Include document lifecycle fields: `owner_team`, `review_cadence`, and `last_validated_at`.
- Include retrieval aids: `primary_intents`, `secondary_intents`, and `dependency_domains`.

### Agent Retrieval Hints
- Prefer tags and service filters first.
- If no service is detected, route by category and incident phase keywords.
- Use architecture and policy docs to ground cross-service answers when runbook evidence is incomplete.


Targeted Expansion Addendum
- Add explicit rollback trigger thresholds tied to business KPIs.
- Capture a before/after metric snapshot for every mitigation step.
- Maintain a bounded decision log to avoid conflicting concurrent actions.
- Include a dependency verification pass before declaring resolution.
- Require ownership and due date for every temporary override cleanup item.
- Add replayable query/command snippets in future revisions for faster triage.
- Improve handoff packet quality for long incidents with clear unresolved risks.


Final Expansion Note
This addendum extends operational depth with additional verification checkpoints, mitigation traceability requirements, and post-incident quality controls so responders can make faster, safer decisions under pressure while preserving evidence integrity.

