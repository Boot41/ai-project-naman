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

