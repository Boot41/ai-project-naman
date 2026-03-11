# Service Dependencies

Service Dependencies

## Architecture Explanation
This document defines the dependency model for the OpsCopilot microservices platform so incident responders can quickly understand blast radius and likely fault origin. Dependencies are categorized as synchronous request dependencies, asynchronous event dependencies, and external dependencies. A dependency is considered critical if its failure can prevent order placement, authentication, or core platform access. The graph is intentionally directional: service A depends on service B when A cannot complete a required operation without B or without a bounded fallback.

Core services in scope:
- api-gateway
- auth-service
- payment-service
- user-service
- order-service
- inventory-service
- notification-service
- search-service
- analytics-service

## Service Relationships
api-gateway
- Synchronous dependencies: auth-service (token validation), order-service, user-service, payment-service, search-service, inventory-service.
- Operational role: central ingress and policy enforcement. Symptoms here can be caused by downstream failures, so gateway alarms are often effect rather than cause.

auth-service
- Synchronous dependencies: user-service account status data, auth datastore.
- Consumers: api-gateway and internal service clients requiring token validation.
- Notes: failure often appears as widespread 401/503 across unrelated routes.

user-service
- Synchronous dependencies: user datastore.
- Consumers: auth-service, order-service, api-gateway profile routes.
- Notes: account status and profile lookups can indirectly impact login and checkout ownership validation.

order-service
- Synchronous dependencies: inventory-service for reservation checks, payment-service for charge authorization/capture, user-service for account linkage.
- Asynchronous dependencies: notification-service, analytics-service via emitted order events.
- Notes: orchestration service; high fan-out makes it sensitive to latency in any critical downstream.

payment-service
- Synchronous dependencies: external payment provider API, auth-service (service auth), payment datastore.
- Asynchronous dependencies: notification-service and analytics-service for payment event propagation.
- Notes: direct revenue dependency; timeout amplification risk when retries are misconfigured.

inventory-service
- Synchronous dependencies: inventory datastore.
- Asynchronous consumers: search-service index ingestion, analytics-service.
- Notes: stale inventory can cascade into search inaccuracies and checkout reservation failures.

notification-service
- Asynchronous dependencies: event bus, messaging provider (email/SMS/push).
- Upstream producers: order-service, payment-service.
- Notes: usually non-blocking for transaction completion but critical for customer communication and trust.

search-service
- Synchronous dependencies: search cluster, optional auth-service/user-service enrichment.
- Asynchronous dependencies: inventory-service and order-service event streams for index freshness.
- Notes: can degrade independently in freshness vs availability dimensions.

analytics-service
- Asynchronous dependencies: event streams from all domain services, analytics datastore.
- Consumers: operations dashboards, business reporting, incident impact analysis.
- Notes: platform may remain transactional even when analytics is delayed, but observability and decision quality degrade.

## Dependency Chains
Critical synchronous chains:
1. Platform access chain
   client -> api-gateway -> auth-service -> user-service/datastore
   Failure impact: widespread inability to authenticate or access protected APIs.

2. Checkout chain
   client -> api-gateway -> order-service -> inventory-service (reserve)
   then order-service -> payment-service -> external provider
   then order-service state commit
   Failure impact: degraded or failed order placement, direct revenue loss.

3. Search query chain
   client -> api-gateway -> search-service -> search cluster
   optional enrichment from auth-service/user-service
   Failure impact: discoverability loss, increased support tickets, possible conversion drop.

High-value asynchronous chains:
1. Order completion chain
   order-service event -> notification-service -> customer channel delivery.

2. Payment telemetry chain
   payment-service event -> analytics-service dashboards and alerts.

3. Inventory freshness chain
   inventory-service events -> search-service ingestion -> updated search results.

4. Platform observability chain
   service logs/metrics/traces -> analytics-service tooling -> OpsCopilot correlation and incident triage.

Transitive Dependency Risks
- auth-service degradation can indirectly impact every protected route because api-gateway depends on auth decisions before routing.
- payment-service issues can backpressure order-service, then spill into api-gateway via retries and increased timeout rates.
- inventory event lag can create search stale data; stale search can drive failed checkouts if unavailable items are selected.
- analytics-service lag does not always break customer transactions but increases mean time to detect and assess incidents.

Failure Containment Guidance
- Prefer localized fail-fast for unhealthy downstream dependencies rather than broad retries.
- Enforce retry budgets once per chain, not at every hop.
- Use degraded modes where available:
  - search-service without personalization
  - notification-service queued retries without blocking order completion
  - payment fallback provider routing for eligible methods
- Apply route-level controls at api-gateway to protect critical paths during partial incidents.

Dependency Priority Model
- Priority A (must restore first): api-gateway, auth-service, order-service, payment-service.
- Priority B (restore for correctness and conversion): inventory-service, search-service.
- Priority C (restore for communication and visibility): notification-service, analytics-service.

Operational Use In Incident Response
1. Identify failing user journey (login, checkout, search, order status).
2. Map journey to primary chain and immediate dependencies.
3. Check transitive dependencies that commonly masquerade as primary faults.
4. Confirm whether impact is synchronous availability, asynchronous freshness, or telemetry visibility.
5. Select mitigation with lowest blast radius first: rollback, traffic shaping, degraded mode, then broader failover.

This dependency model should be used jointly with service runbooks and incident severity policy to prioritize recovery actions and escalation timing.

During high-uncertainty incidents, responders should explicitly mark each dependency as healthy, degraded, or unknown to avoid assumption drift. Unknown dependencies should be treated as potential amplifiers until verified by telemetry.

