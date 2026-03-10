# Auth Service Runbook

## Service Description
auth-service provides identity verification and token services for the platform. It handles user credential validation, issues JWT access tokens, validates token signatures and claims for internal services, and exposes token refresh endpoints where configured. api-gateway relies on auth-service for request authentication decisions, while user-service supplies account profile and status checks. auth-service also maintains password hash policy, account lockout counters, and audit logging for authentication events. Because all `/api/v1/*` requests require valid bearer tokens, auth-service degradation rapidly becomes a platform-wide availability incident. The service runs as stateless API pods plus a backing datastore for users and refresh token metadata, with optional cache for token introspection. Operational targets are login success rate above 99 percent for valid credentials, token validation latency p95 below 120 ms, and internal auth error rate below 0.2 percent.

## Common Failure Modes
1. Datastore latency or connection pool exhaustion. Login and refresh flows stall when user lookups or token metadata writes are slow.
2. JWT signing key mismatch during rotation. Newly issued tokens fail validation across services due to inconsistent key versions.
3. Clock skew between nodes. Tokens appear expired or not yet valid, causing widespread 401 responses.
4. Cache inconsistency in introspection mode. Stale token revocation state produces false accepts or false rejects.
5. Password hash cost misconfiguration. Excessive bcrypt/argon parameters spike CPU and degrade login throughput.
6. Account lockout threshold regression. Legitimate users are locked after too few failures due to configuration bug.
7. Dependency outage from user-service. Account status checks timeout and block login decisions.
8. TLS or certificate errors on internal calls from api-gateway to auth-service.

## Important Metrics
- Login throughput and latency (`login_rps`, `login_latency_p95`).
- Token validation latency and error rate.
- HTTP status distribution for `/auth/login`, `/auth/refresh`, `/auth/validate`.
- Invalid token reasons (`expired`, `signature_invalid`, `issuer_mismatch`, `audience_mismatch`).
- Datastore health (query latency, pool utilization, timeout count, replication lag).
- Cache performance (hit rate, stale read count, eviction rate).
- CPU and memory utilization per pod, with focus on hash operation saturation.
- Account lockout rates and failed login trends by source network.
- Key version metrics (active signing key ID distribution, validation key set sync status).
- Audit log delivery lag and failure count.

## Investigation Steps
1. Determine failure pattern: login failures only, validation failures only, or global auth unavailability.
2. Check platform-wide 401/403 trends from api-gateway. Sharp simultaneous increases indicate auth-service or key-sync issue.
3. Inspect auth-service latency and error dashboards. Confirm whether p95/p99 rose before or after error-rate spike.
4. Validate datastore health first. High DB latency and pool exhaustion are common root causes for login and refresh failures.
5. Verify key rotation status. Compare signing key ID in issued tokens with key set loaded by validators across services.
6. Check system clocks and NTP sync on auth and gateway nodes if “token expired” errors spike unexpectedly.
7. Review recent deploys/config changes: hash cost, lockout threshold, JWT issuer/audience claims, cache TTL.
8. Sample failed authentication logs by correlation ID. Distinguish invalid credentials from infrastructure errors.
9. Test known-good credentials in controlled environment and observe raw endpoint responses.
10. Validate user-service dependency path. If account status check is timing out, inspect circuit breaker behavior and fallback policy.
11. Check TLS handshake errors and certificate validity between gateway and auth-service.
12. Evaluate whether failure is regional or global by comparing zone-level metrics and synthetic probes.
13. Update incident timeline with evidence and candidate root causes; identify if immediate containment is possible.

## Recovery Steps
1. If datastore bottleneck is primary, scale DB pool and auth pods, then reduce non-essential queries in login path.
2. If key mismatch occurred, roll forward or rollback to a consistent key set and force validator cache refresh across services.
3. If clock skew detected, correct NTP synchronization and temporarily widen token clock tolerance only as emergency override.
4. If hash-cost regression caused CPU saturation, revert config to known baseline and redeploy auth-service.
5. If lockout misconfiguration caused mass lockouts, restore threshold policy and run controlled unlock process for affected accounts.
6. If user-service dependency is unstable, apply fallback policy for non-critical account attributes while preserving security checks.
7. If TLS internal cert issue exists, redeploy valid cert chain and confirm trust bundle on both caller and callee.
8. Drain unhealthy pods with repeated timeout or memory pressure symptoms.
9. After stabilization, verify login success rate, token validation latency, and reduction in 401 anomalies for at least 30 minutes.
10. Audit token issuance and revocation events during incident window for security review.

## Escalation Contacts
- Primary On-Call: Identity Platform Engineer (`identity-primary`).
- Secondary On-Call: Access Reliability Engineer (`identity-secondary`).
- Security Escalation: Security Operations Duty Officer for suspected token forgery, unauthorized access, or key compromise.
- Datastore Escalation: Database Reliability Engineer if query latency remains above threshold after service scale-out.
- Cross-Service Escalations:
  - api-gateway authentication failures: Edge Platform SRE.
  - user-service account lookup failures: User Domain On-Call.
- Incident Commander: Required for SEV1 and any incident affecting global authentication.
- Escalation Triggers:
  - Global login success rate below 85 percent for 10 minutes.
  - Token validation error rate above 5 percent on protected routes.
  - Evidence of signing key inconsistency across more than one zone.
  - Suspected security incident involving credential stuffing or token abuse.
- Regulatory/Compliance Trigger:
  - Any confirmed unauthorized token acceptance requires immediate security incident protocol activation and compliance notification.

## Additional Operational Data Pack

## Scenario Matrix For auth-service
1. Regional dependency degradation with stable local CPU: Trigger synthetic probes from two regions, compare upstream RTT variance, and mark incident as network-path sensitive if delta exceeds 35 percent.
2. Configuration drift after deployment: Validate active runtime config checksum, compare with Git artifact checksum, and confirm no sidecar override injected stale values.
3. Slow-burn saturation event: Watch queue depth slope across 30 minutes, not just absolute threshold, because early trend often predicts failure before SLO breach.
4. Partial dependency outage: Identify affected API operations by endpoint and method, then switch to route-level degraded behavior only for impacted paths.

## Expanded Investigation Checklist
- Confirm alert source quality: classify as customer-reported, synthetic, metric, or log anomaly.
- Build a two-axis blast map: business workflow impact vs technical component impact.
- Capture first bad request ID and first recovery request ID.
- Validate retry policy at every caller layer to avoid multiplicative traffic growth.
- Check timeout budget consistency between caller and callee.
- Compare deployment timeline against error timeline with exact minute precision.
- Validate secrets and certificates age, issuance timestamp, and rotation policy status.
- Inspect network path health: DNS lookup latency, TCP handshake failures, TLS negotiation latency.
- Evaluate storage pressure: IOPS saturation, replication lag, and write queue backlog.
- Collect five representative failing samples and five successful samples for diff analysis.

## Operational Signals To Add To Dashboards
- Error budget burn rate (5-minute and 1-hour windows).
- Dependency latency variance, not just mean and percentile.
- Retry amplification ratio (outbound requests / inbound requests).
- Degraded-mode activation count and duration.
- Configuration reload events and rollout wave status.
- Queue recovery half-life after mitigation.
- Saturation early warning score combining CPU throttling + queue growth + timeout drift.

## Recovery Playbooks (Detailed)
1. Contain
- Freeze non-essential deploys for impacted service and direct dependencies.
- Activate lowest-risk degraded path that preserves core business transaction correctness.
- Lower inbound concurrency if dependency is unstable to prevent cascading saturation.

2. Stabilize
- Scale only where bottleneck evidence exists; avoid blind scale-out that increases coordination cost.
- Tune retries to fail-fast during active dependency outage.
- Protect persistence tier by pausing low-priority background jobs.

3. Verify
- Confirm p95 and p99 returning toward baseline with three consecutive clean intervals.
- Validate business KPI recovery (login success, checkout completion, search success) alongside infra metrics.
- Confirm no hidden backlog remains in async pipelines.

4. Exit
- Remove temporary overrides in reverse order of introduction.
- Keep heightened alert sensitivity for one hour post-recovery.
- Publish short recovery bulletin with residual risk statement.

## Escalation Enhancement Rules
- Auto-escalate if no measurable improvement within 15 minutes of first mitigation.
- Escalate immediately if integrity or security controls are bypassed.
- Add domain owner to bridge when incident crosses service boundary.
- Require incident commander for multi-service degradation even if initial severity is moderate.

## Post-Incident Data Capture Template
- Trigger condition and earliest confirmed symptom.
- Primary and contributing causes.
- What detection signal should have fired earlier.
- What containment control worked fastest.
- Which manual step should be automated.
- Follow-up actions with owner, due date, and measurable success criteria.


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
