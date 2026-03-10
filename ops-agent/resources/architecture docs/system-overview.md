# System Overview

## Architecture Explanation
OpsCopilot operates on a microservices commerce platform where api-gateway is the single ingress for client and partner traffic. The gateway handles TLS termination, request identity propagation, and policy enforcement before forwarding to domain services. Core domain services include auth-service for identity and token operations, user-service for profile and account metadata, order-service for order lifecycle orchestration, inventory-service for stock and availability state, payment-service for authorization/capture operations, notification-service for outbound customer messaging, search-service for catalog and lookup queries, and analytics-service for event aggregation and reporting. Each service publishes structured logs, metrics, and traces to a centralized observability stack used by operations engineers and OpsCopilot incident workflows.

The runtime topology is distributed across multiple availability zones. Services are containerized and horizontally scaled. Service discovery and internal DNS provide endpoint resolution, while a message bus transports asynchronous events between domain services and analytics pipelines. Data ownership is bounded by service: payment-service owns transaction records, order-service owns order state, inventory-service owns stock state, and search-service owns query and index-read APIs while ingesting updates from other domains. This separation keeps ownership clear during incidents and reduces cross-service write contention.

OpsCopilot’s investigation flow starts with ingestion of alerts and telemetry. It correlates anomalies across traffic, error, latency, and saturation signals, then maps symptoms to dependency chains. For example, a checkout failure can originate from payment-service provider latency, order-service retry storms, auth token validation issues, or gateway route policies. OpsCopilot’s job is to reduce time to evidence by linking a symptom in one service to likely upstream or downstream contributors.

## Service Relationships
- api-gateway fronts all user-facing calls and is tightly coupled to auth-service for token validation and identity headers.
- auth-service depends on user-service and backing data stores for account status and credential metadata.
- order-service coordinates with inventory-service for reservation, payment-service for charge execution, and notification-service for order confirmations.
- payment-service receives authorization/capture requests from order-service via gateway paths and emits events to notification-service and analytics-service.
- inventory-service publishes stock-change events consumed by search-service indexing pipelines and analytics-service.
- search-service serves low-latency query workloads and depends on inventory-service and order-service event streams for index freshness.
- notification-service is mostly asynchronous and relies on completed events from order-service and payment-service.
- analytics-service consumes platform events from all services and provides dashboards used for incident impact assessment.

Relationships are not only call-level but also operational. Gateway retries can amplify pressure on payment-service. Search index lag can expose inventory inconsistencies even if inventory-service itself is healthy. Auth latency can appear as generalized API latency because every protected route passes through token validation. This is why incident diagnosis must include both direct dependency checks and transitive dependencies.

## Dependency Chains
Primary synchronous chains:
1. Login path: client -> api-gateway -> auth-service -> user datastore.
2. Checkout path: client -> api-gateway -> order-service -> payment-service -> external provider; parallel validation with auth-service and inventory-service reservation checks.
3. Search path: client -> api-gateway -> search-service -> search cluster; optional enrichment from auth-service and user-service context.
4. Order status path: client -> api-gateway -> order-service -> user-service (ownership checks) and payment-service (payment state).

Primary asynchronous chains:
1. Order completion -> notification-service for customer communication.
2. Payment authorization/capture events -> analytics-service and notification-service.
3. Inventory updates -> search-service ingestion -> analytics-service.
4. Service telemetry -> analytics-service dashboards -> OpsCopilot alerting and incident correlation.

Operational dependency priorities:
- Tier 1 availability dependencies: api-gateway, auth-service, payment-service, order-service.
- Tier 2 customer-experience dependencies: search-service, inventory-service.
- Tier 3 communication/reporting dependencies: notification-service, analytics-service.

Failure propagation examples:
- If auth-service latency increases, api-gateway request queues grow, causing platform-wide p99 latency increase.
- If payment provider latency spikes, order-service retries can saturate payment-service, then gateway timeout rates rise.
- If inventory event ingestion stalls, search freshness degrades, causing stale availability results and potential order failures later.
- If analytics-service lags, direct customer transactions continue, but incident visibility and impact quantification degrade.

Investigation Entry Points For Operations
1. Start with gateway golden signals to determine whether issue is global or route-specific.
2. Pivot to service-level dashboards based on failing routes and error signatures.
3. Check dependency health in chain order (caller, callee, external dependency) to avoid misattributing symptoms.
4. Validate whether issue is synchronous request path, asynchronous pipeline, or both.
5. Use trace IDs and correlation IDs to stitch events across services and build a concrete timeline.

Reliability Controls
- Circuit breakers and fail-fast timeouts on critical upstream calls.
- Idempotency keys on payment and order mutation paths.
- Rate limiting and retry budgets at gateway and service levels.
- Autoscaling based on CPU plus queue-depth signals for burst handling.
- Runbooks and incident policy that define escalation thresholds by severity.

This architecture favors clear ownership, explicit dependency boundaries, and observability-first operations so incidents can be diagnosed quickly with evidence rather than assumptions.

Operationally, change management should follow dependency-aware sequencing: stabilize auth and gateway first, then checkout path services, then search freshness and downstream reporting. This ordering minimizes user-visible impact during multi-service incidents.

## Additional Architecture Navigation Data

## Dependency Risk Taxonomy
- Hard dependency: request cannot complete without downstream success.
- Soft dependency: request can complete in degraded mode.
- Async dependency: impact appears as lag, freshness drift, or delayed communication.
- External dependency: third-party or platform service with separate operational controls.

## Priority Recovery Ordering
1. Authentication and ingress path stability.
2. Revenue-critical transaction path stability.
3. Discovery and correctness path stability.
4. Communication and analytics path stability.

## Cross-Service Failure Patterns
- Shared dependency slowdown causing broad latency increase.
- One-service retry storm saturating adjacent services.
- Async backlog masking success until delayed side effects appear.
- Control-plane incidents that look like app errors but originate in orchestration or networking.

## Standard Triage Queries
- Which user journey is currently broken?
- Which dependency chain supports that journey?
- Which node in chain first crossed SLO boundary?
- Which mitigation has lowest blast radius and fastest reversibility?

## Architecture Evidence Model For Investigations
- Time axis: first anomaly, first alert, first mitigation, stabilization, closure.
- Component axis: ingress, identity, domain service, persistence, async pipeline, external provider.
- Impact axis: availability, latency, correctness, freshness, observability.

## Operational Design Guardrails
- Enforce bounded retries and timeout budgets at one layer only.
- Keep idempotency at mutation boundaries.
- Prefer fail-fast plus explicit degradation over hidden queue growth.
- Preserve request correlation IDs across every synchronous and async boundary.
- Define ownership for each dependency edge, not just each service node.

## Expansion Guidance For Future Docs
- For long architecture guides, use segmented structure:
  - <doc>/index.md
  - section_01_overview.md
  - section_02_dependency_graph.md
  - section_03_failure_patterns.md
- Keep section files independently retrievable with local context headers.
- Ensure section names reflect investigation intent (diagnose, contain, recover, verify).


## Supplemental Deep-Dive Operations Appendix

## Decision Tree For Active Incidents
1. Is customer impact rising right now?
- Yes: prioritize containment over diagnosis depth.
- No: complete root-cause isolation before applying risky mitigations.
2. Is impact isolated to one user journey?
- Yes: isolate by endpoint and dependency chain.
- No: inspect shared controls (gateway, auth, networking, runtime config).
3. Is integrity risk present?
- Yes: pause risky mutations, engage compliance/security/finance path immediately.
- No: continue with staged degradation and traffic management.

## Advanced Evidence Collection Pack
- Capture per-minute error-rate and latency percentile snapshots during the first 20 minutes.
- Preserve representative request/trace IDs for each affected endpoint class.
- Compare successful and failing payload classes to detect conditional failures.
- Build dependency health matrix with states: healthy, degraded, unknown, failed.
- Attach rollout metadata to timeline: artifact id, config hash, zone, and rollout wave.

## Containment Patterns Library
- Pattern A: Route shaping
  - reduce non-critical traffic,
  - enforce hard concurrency caps,
  - preserve critical business path.
- Pattern B: Dependency isolation
  - disable optional enrichment,
  - short-circuit failing upstream calls,
  - enable fallback response mode.
- Pattern C: Retry suppression
  - remove nested retries,
  - enforce backoff with jitter,
  - cap outstanding inflight calls.
- Pattern D: Backlog protection
  - pause low-priority consumers,
  - prioritize customer-facing workflows,
  - monitor queue drain half-life.

## Recovery Confidence Checklist
- Recovery confidence should not rely on one metric.
- Require concurrent improvement in:
  - user-facing success metrics,
  - service p95/p99 latency,
  - dependency error rates,
  - queue lag and backlog,
  - saturation and throttling indicators.
- Keep 30 to 60 minute observation window before declaring full closure.

## Operational Debt Log Template
- What temporary override was applied?
- Who owns rollback and by when?
- What metric confirms rollback safety?
- What automation would remove this manual step next time?
- What test should be added so this failure pattern is caught earlier?

## Cross-Team Coordination Model
- SRE: incident command, system stabilization, and rollback orchestration.
- Domain team: service-specific mitigations and code/config ownership.
- Security/compliance: integrity and policy exception decisions.
- Data/analytics: impact quantification and recovery confirmation on reporting side.
- Support/comms: external-facing updates and customer narrative alignment.

## Post-Recovery Hardening Tasks
- Add detectors for precursor signals seen in this incident class.
- Create safe-mode configuration presets with explicit exit criteria.
- Simulate similar failure in staging with replayed traffic pattern.
- Update runbooks and postmortem templates with new validated steps.
- Audit dashboard coverage to ensure first-response visibility within one pane.


## Targeted Expansion Addendum
- Add explicit rollback trigger thresholds tied to business KPIs.
- Capture a before/after metric snapshot for every mitigation step.
- Maintain a bounded decision log to avoid conflicting concurrent actions.
- Include a dependency verification pass before declaring resolution.
- Require ownership and due date for every temporary override cleanup item.
- Add replayable query/command snippets in future revisions for faster triage.
- Improve handoff packet quality for long incidents with clear unresolved risks.


## Final Expansion Note
This addendum extends operational depth with additional verification checkpoints, mitigation traceability requirements, and post-incident quality controls so responders can make faster, safer decisions under pressure while preserving evidence integrity.


## Closure Confidence Addendum
- Confirm customer-facing KPIs are stable across consecutive windows.
- Confirm dependency metrics returned to expected variance range.
- Confirm no hidden operational backlog remains unowned.
- Confirm response artifacts are complete for audit and future replay.
- Confirm preventive actions are scheduled with accountable owners.
