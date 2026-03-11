# Incident Response Policy

## Incident Severity Definitions
This policy defines severity levels, ownership, process, and escalation rules for operational incidents affecting the OpsCopilot platform. Severity is assigned based on customer impact, business risk, data integrity risk, security exposure, and expected duration. Severity can be raised or lowered as evidence evolves.

SEV1 (Critical)
- Criteria:
  - Platform-wide outage of critical workflows (login, checkout, core API access).
  - Sustained error rate greater than 20 percent on critical routes.
  - Security or data integrity threat with active or likely customer harm.
- Expectations:
  - Immediate incident declaration.
  - Incident commander assigned within 5 minutes.
  - Cross-functional bridge active continuously.
  - Executive and stakeholder updates every 15 minutes.

SEV2 (High)
- Criteria:
  - Major degradation of critical user journeys with partial functionality remaining.
  - Significant latency causing material conversion or operational impact.
  - Multi-service incident with growing blast radius if untreated.
- Expectations:
  - Incident declaration within 10 minutes of confirmation.
  - Incident commander assigned within 10 minutes.
  - Stakeholder updates every 30 minutes.

SEV3 (Moderate)
- Criteria:
  - Localized service degradation with workaround available.
  - Non-critical feature outage with bounded customer impact.
  - Asynchronous pipeline delay affecting freshness or reporting.
- Expectations:
  - On-call service owner leads response.
  - Escalate to incident commander if duration exceeds 30 minutes or impact expands.
  - Stakeholder updates every 60 minutes.

SEV4 (Low)
- Criteria:
  - Minor defects, transient alerts, or low-risk degradation.
  - No meaningful customer impact and no active business risk.
- Expectations:
  - Track in operations backlog and resolve in normal work cycle.
  - Upgrade severity if impact changes.

## Response Process
1. Detection and Triage
- Sources: automated alerts, synthetic probes, customer reports, internal monitoring.
- First responder validates alert signal, confirms affected service or journey, and checks for false positives.
- Open incident channel using standard naming format (`inc-YYYYMMDD-<service>-<summary>`).
- Record first known symptom timestamp and impacted metrics.

2. Incident Declaration
- Assign preliminary severity using criteria above.
- Declare incident when impact is confirmed, even if root cause unknown.
- Nominate roles:
  - Incident Commander (decision authority and timeline ownership)
  - Operations Lead (technical coordination)
  - Communications Lead (status updates)
  - Subject Matter Leads (service-specific responders)

3. Stabilize and Contain
- Prioritize customer impact reduction over full root-cause proof.
- Choose fastest safe containment action:
  - rollback recent change
  - disable risky feature flag
  - apply route-level traffic shaping
  - activate degraded mode
  - fail over to backup dependency
- Document every mitigation with timestamp, owner, and expected effect.

4. Diagnose and Recover
- Build evidence-based timeline from logs, traces, metrics, and change events.
- Validate dependency chain health from caller to callee and external providers.
- Avoid uncoordinated parallel changes that obscure causality.
- Confirm recovery using objective service-level indicators before closure.

5. Resolution and Closure
- Incident can move to resolved only when:
  - customer-impacting symptoms are cleared
  - key metrics remain stable for at least 30 minutes
  - no critical backlog remains that could immediately re-trigger impact
- Assign postmortem owner before channel closure.
- Capture temporary overrides and cleanup tasks with due dates.

## Escalation Guidelines
General Escalation Rules
- Escalate early when blast radius is uncertain or growing.
- Escalate immediately for any suspected financial integrity or security issue.
- If no clear containment path within 20 minutes for SEV1/SEV2, escalate to broader engineering leadership.
- If external provider contributes materially, open vendor incident ticket within 10 minutes of confirmation.

Role-Based Escalation Matrix
- api-gateway incidents: Edge Platform SRE primary.
- auth-service incidents: Identity Platform primary; Security involved for token or auth abuse anomalies.
- payment-service incidents: Payments primary; Finance Ops engaged for duplicate charge or settlement concerns.
- order/inventory incidents: Commerce Platform primary.
- search-service incidents: Search Platform primary; infra specialist for cluster-level failures.
- notification-service incidents: Messaging Platform primary.
- analytics-service incidents: Data Platform primary.

Mandatory Escalation Triggers
- SEV1 criteria met at any point.
- Checkout completion below 90 percent for 10 minutes.
- Global login failure above 15 percent for 10 minutes.
- Search success below 92 percent for 10 minutes with customer-facing impact.
- Any evidence of unauthorized access, token compromise, or data exposure.
- Any duplicate-charge detector confirmation.

Communications Policy
- Internal updates must include:
  - current severity
  - customer impact statement
  - known facts vs assumptions
  - mitigation actions in progress
  - next update time
- External or customer-facing communication must be approved by Communications Lead and Incident Commander.
- Avoid speculative root-cause claims before evidence is validated.

Operational Standards
- All incident decisions and actions must be timestamped.
- Use correlation IDs when sharing evidence from logs/traces.
- Prefer reversible changes first; high-risk changes require explicit commander approval.
- Preserve forensic artifacts for security or compliance incidents.
- For long incidents, rotate responders to prevent fatigue and decision errors.

Post-Incident Requirements
- Postmortem required for all SEV1 and SEV2 incidents, and SEV3 incidents with repeat pattern.
- Postmortem must include root cause, contributing factors, impact quantification, mitigation timeline, and preventive actions.
- At least one preventive action must address detection quality, and one must address containment speed.
- Action items must have owner, due date, and verification criteria.

Policy Governance
- This policy is owned by Operations Engineering.
- Review cadence is quarterly or immediately after major SEV1 events.
- Changes require approval from SRE manager, Security representative, and domain owners for impacted services.

