# Payment Service Runbook

## Service Description
payment-service authorizes and captures customer payments for orders, handles idempotency for retry-safe checkout operations, writes transaction state, and emits events to notification-service and analytics-service. It integrates with third-party payment processors through a provider abstraction and supports card, wallet, and stored payment methods. The service receives requests from order-service through api-gateway and depends on auth-service for service-to-service token validation and user-service for billing profile lookup. Critical data paths include authorization latency, provider response mapping, and reconciliation state transitions. payment-service is classified as tier critical because failures directly prevent checkout completion and can create revenue impact. Operational SLO targets are p95 authorization latency below 450 ms, success rate above 99.3 percent for healthy provider windows, and duplicate charge rate effectively zero with idempotency keys.

## Common Failure Modes
1. Upstream provider latency surge. External processor response times increase from sub-300 ms to multi-second range, causing timeout and retry storms.
2. Provider partial outage by payment method. Card tokens may fail while wallet transactions continue, creating inconsistent customer experience.
3. Database lock contention on transaction tables. High write concurrency or long-running reconciliation job increases commit latency and deadlocks.
4. Idempotency cache eviction bug. Replayed checkout calls can bypass deduplication and create duplicate authorization attempts.
5. Secrets rotation mismatch. Expired provider API key or certificate leads to immediate authorization failures.
6. Message queue lag for post-payment events. Notification and analytics updates delay while core charge appears successful.
7. Regional network degradation. Cross-region provider calls fail intermittently with connection resets.
8. Currency formatting or rounding regression after deployment, leading to provider validation errors.

## Important Metrics
- Authorization latency (`authz_latency_p50/p95/p99`) split by provider and payment method.
- Capture latency and failure rate.
- Provider error code distribution (`timeout`, `decline`, `auth_failed`, `rate_limited`, `invalid_request`).
- Success rate by route and method (`/payments/authorize`, `/payments/capture`).
- Idempotency effectiveness (`idempotency_hit_rate`, duplicate request suppression count).
- Transaction DB health (commit latency, lock wait time, deadlock count, replication lag).
- Queue and event metrics (`payment_events_lag_seconds`, consumer backlog).
- Resource saturation (CPU, memory, threadpool queue, connection pool utilization).
- Financial safety metrics (duplicate charge detector, authorization without order match count).
- External dependency status (provider health API, DNS and TLS handshake metrics).

## Investigation Steps
1. Confirm symptom type: high latency, elevated failures, or financial integrity risk. If duplicate-charge alarms fire, treat as priority containment.
2. Inspect service dashboard for the last 2 hours and identify onset time, dominant endpoint, and payment method scope.
3. Split errors by provider and error code. Provider-specific failures usually indicate external issue or credential mismatch.
4. Compare internal processing time vs provider roundtrip. If internal time is stable but roundtrip is high, engage provider fallback strategy.
5. Check recent changes: payment-service deploy, provider SDK update, secrets rotation, DB migration, or configuration updates.
6. Validate secret versions and cert expiration timestamps in runtime environment. Confirm pods loaded latest secret revision.
7. Query transaction DB for lock waits and deadlocks around incident window. Identify blocking queries or stalled background jobs.
8. Inspect idempotency behavior. Sample repeated request IDs and verify only one authorization is persisted per key.
9. Check order-service and api-gateway logs for timeout cascades. Determine whether retries are multiplying load on payment-service.
10. Validate queue health for downstream events. Ensure capture success is not masking delayed notifications or analytics gaps.
11. Run synthetic canary authorization against test merchant account to isolate provider path from production customer data.
12. Assess blast radius by region and payment method to decide whether partial disablement is safer than global outage behavior.
13. Document evidence in incident channel: first failure timestamp, affected provider, financial risk indicators, and ongoing mitigations.

## Recovery Steps
1. If provider latency is primary cause, enable secondary provider routing for eligible payment methods and reduce upstream timeout to fail fast.
2. If provider credentials are invalid, rotate secrets to known good values and restart pods with verified environment version.
3. If DB contention is primary, pause heavy reconciliation jobs, add temporary index if pre-approved, and scale read/write pool cautiously.
4. If retry storm detected, enforce stricter idempotency and backoff policy from order-service and api-gateway.
5. If duplicate-charge risk emerges, temporarily disable captures for affected method, allow authorization-only, and trigger finance guardrail workflow.
6. Roll back recent deployment if regression correlates with onset and no quick config fix is available.
7. Drain unhealthy instances with high error rates or stale secrets; replace with fresh pods after readiness checks pass.
8. When stabilized, replay safely queued events for notification-service and analytics-service with deduplication enabled.
9. Validate recovery with real-time KPIs: success rate normalization, p95 latency below target, duplicate-charge detector clear.
10. Run post-recovery audit query to verify transaction state consistency between payment-service and order-service.

## Escalation Contacts
- Primary On-Call: Payments Platform Engineer (`payments-primary`).
- Secondary On-Call: Checkout Reliability Engineer (`checkout-secondary`).
- Financial Risk Escalation: Finance Operations Duty Lead for duplicate charge or missing capture concerns.
- External Escalation: Payment Provider Technical Support via enterprise hotline and incident ticket channel.
- Cross-Service Escalations:
  - order-service timeout cascade: Commerce On-Call.
  - auth token errors: Identity On-Call.
  - gateway saturation caused by retries: Edge SRE.
- Incident Commander: Mandatory for SEV1 and for any SEV2 with financial risk indicators.
- Escalation Triggers:
  - Checkout success rate below 90 percent for 10 minutes.
  - p95 authorization latency above 1.2 seconds for 15 minutes.
  - Duplicate charge detector > 0 confirmed events.
  - Provider unreachable across two regions with no failover path.
- Compliance Notification Trigger:
  - Any suspected financial integrity breach requires immediate notification to Security and Compliance within 15 minutes of confirmation.

