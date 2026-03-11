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

