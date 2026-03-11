# Api Gateway Runbook

## Service Description
api-gateway is the public ingress for all client and partner traffic. It terminates TLS, validates JWT tokens through auth-service, applies rate limits, enforces request size limits, injects request IDs, and routes traffic to downstream services. In the current platform, most user-facing operations pass through api-gateway first, including authentication, checkout, order status, profile updates, and search queries. The service runs behind a cloud load balancer with multiple gateway pods distributed across availability zones. The gateway maintains a routing table sourced from service discovery, caches auth validation responses for a short interval, and emits access logs with latency, status code, route key, upstream target, and retry count. Because all traffic converges here, api-gateway is a high blast-radius component; partial degradation can look like random failures across unrelated products. The operational objective is to keep p99 latency below 350 ms, 5xx under 0.5 percent, and authentication pass-through errors below 0.2 percent.

## Common Failure Modes
1. Upstream timeout amplification. A single slow dependency, often payment-service or search-service, causes queueing inside gateway worker pools and raises end-to-end latency for unrelated routes.
2. Route misconfiguration after deployment. Incorrect path matching, header rewrites, or service discovery tags send traffic to wrong upstream version, causing 404/502 spikes.
3. JWT validation dependency pressure. auth-service latency or connection errors lead to elevated 401/503 responses for otherwise valid users.
4. Rate limiter state-store failure. Redis or in-memory shard imbalance produces false positives, rejecting normal traffic with 429.
5. TLS certificate rotation issues. Expired or mismatched certificate chain causes handshake failures and apparent outage from external clients.
6. Connection pool exhaustion. Too many downstream keepalive sockets or slow close behavior leads to “no healthy upstream” and reset storms.
7. Logging or tracing backpressure. Blocking log sinks can increase CPU and response latency under high write volume.

## Important Metrics
- Request volume by route (`requests_per_second`, split by method and path template).
- Latency percentiles (`gateway_latency_p50/p95/p99`) and upstream latency contribution.
- HTTP status distribution (`2xx`, `4xx`, `5xx`) with focus on `502`, `503`, `504`, and `429`.
- Auth dependency health (`auth_validation_latency_p95`, `auth_validation_error_rate`).
- Upstream timeout count and retry count by service.
- Worker saturation (`active_workers`, queue depth, event loop lag).
- Connection metrics (open sockets, pool utilization, connection reset rate).
- Load balancer metrics (healthy targets, TLS handshake errors, accepted connections).
- Resource metrics (CPU throttling, memory RSS, GC pauses if runtime managed).
- Golden signals dashboard: traffic, errors, latency, saturation for gateway and top three upstreams.

## Investigation Steps
1. Confirm incident scope. Check alerts, customer reports, and synthetic probes. Separate global from route-specific impact.
2. Inspect gateway golden signals for the last 60 minutes. Look for sharp step changes at deploy boundaries, autoscaling events, or dependency incidents.
3. Break down errors by route key. If a small subset of routes dominates failures, pivot to associated upstream service runbook.
4. Compare gateway latency to upstream latency. If gateway-only latency rises while upstream remains stable, investigate gateway worker saturation, logging sinks, and local resource pressure.
5. Validate auth dependency. Query auth-service health endpoint and dashboard. If auth latency is elevated, sample failed requests and confirm whether 401 vs 503 is expected.
6. Check load balancer target health and zone distribution. Uneven healthy target counts often indicate node-level networking or bad rollout to one zone.
7. Review last three deployments: gateway config, route map, policy changes, certificate updates, and rate limit profiles. Correlate exact change timestamp with first error spike.
8. Pull structured logs for request IDs from failing routes. Verify upstream target, retry policy, timeout policy, and final response code.
9. Run controlled canary probes from internal network to bypass edge CDN. This helps isolate external TLS/WAF issues from internal routing issues.
10. Validate service discovery state. Ensure endpoints and tags match expected version. Look for stale cache or split-brain registration.
11. Confirm rate-limiter store health. Check Redis latency and hit/miss anomalies; false 429 patterns usually cluster by client segment.
12. Inspect node-level telemetry on overloaded pods: CPU throttling, file descriptor usage, conntrack pressure, and kernel retransmits.
13. Build evidence timeline in incident channel. Include first symptom time, affected routes, likely dependency chain, and current mitigations.

## Recovery Steps
1. If route misconfiguration is confirmed, rollback gateway config to last known good version immediately.
2. If a single upstream is failing, apply temporary route-level circuit breaking and return graceful degradation responses for non-critical endpoints.
3. Increase gateway worker replica count if saturation is confirmed and downstream capacity exists.
4. Reduce retry aggressiveness during dependency outages to prevent retry storms; prefer fail-fast with bounded backoff.
5. If auth-service is bottlenecked, enable short-lived JWT validation cache extension (within policy bounds) and coordinate auth-service scale-out.
6. If certificate issue is detected, deploy validated certificate bundle and trigger load balancer listener reload.
7. If rate-limiter false positives occur, switch to conservative fallback profile (higher threshold, anomaly logging enabled) until state-store is healthy.
8. Drain and replace unhealthy nodes/pods showing connection resets or kernel networking anomalies.
9. After stabilization, gradually restore stricter policies (retry/rate limits/cache TTL) and monitor p95/p99 and error rate for 30 minutes.
10. Record all temporary overrides with expiration timestamps and ownership for cleanup.

## Escalation Contacts
- Primary On-Call: Edge Platform SRE (PagerDuty service `edge-sre-primary`).
- Secondary On-Call: Traffic Engineering (`edge-sre-secondary`).
- Dependency Escalations:
  - auth-service issues: Identity Platform On-Call.
  - payment-service route failures: Payments On-Call.
  - search-service route failures: Search Infra On-Call.
- Incident Commander: Assigned by SRE manager for SEV1/SEV2 events.
- Communications Lead: Operations Duty Manager for stakeholder updates.
- Escalation Triggers:
  - SEV1 declaration criteria met (global 5xx > 10 percent for 10 minutes).
  - p99 latency above 1.5 seconds for critical routes for 15 minutes.
  - Any auth outage affecting login or token validation globally.
  - No clear containment path within 20 minutes of investigation start.
- External Vendor Escalation:
  - Cloud Load Balancer support ticket if target health and TLS failures persist across multiple zones despite internal rollback.

