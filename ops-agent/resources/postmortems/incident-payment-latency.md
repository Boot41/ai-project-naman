# Incident Payment Latency

## Incident Summary
On 2026-02-18, OpsCopilot detected a sustained latency regression in checkout flows tied to payment-service authorization calls. The incident started as a SEV3 at 14:07 UTC when p95 payment authorization latency crossed 700 ms, then escalated to SEV2 at 14:15 UTC after checkout completion rate dropped below 93 percent for two consecutive evaluation windows. Although the platform remained partially available, customer checkout delays increased abandonment and triggered a rise in support contacts. No confirmed duplicate charges were detected, but retry pressure from order-service and api-gateway amplified load and increased timeout frequency. The incident was mitigated by routing eligible transactions to a secondary provider profile, reducing retry amplification, and scaling payment-service worker pools. Full recovery was declared at 15:02 UTC with p95 latency returned to 410 ms and checkout completion restored above 98 percent.

## Timeline
14:03 UTC: Provider latency early warning alert fires for primary payment processor in us-east region; no customer-facing impact yet.
14:07 UTC: payment-service `authz_latency_p95` breaches 700 ms. OpsCopilot correlates with rising provider timeout codes.
14:10 UTC: api-gateway reports increased upstream timeout retries for `/payments/authorize` path. Incident channel opened.
14:12 UTC: order-service checkout success dips from baseline 99 percent to 95 percent. On-call payments engineer acknowledges.
14:15 UTC: Incident reclassified from SEV3 to SEV2 due to sustained checkout degradation.
14:17 UTC: Investigation confirms internal processing time stable; provider roundtrip latency elevated >900 ms p95.
14:20 UTC: Retry storm identified: order-service retry policy plus gateway retries increased effective call volume by 1.8x.
14:24 UTC: Incident commander assigned. Decision made to activate secondary provider for wallet and selected card BIN ranges.
14:28 UTC: Secondary routing enabled for 42 percent of eligible traffic.
14:31 UTC: payment-service pod count increased from 12 to 20 to absorb queued work; queue depth begins dropping.
14:36 UTC: Gateway retry policy reduced for payment routes (max retries from 2 to 1, shorter timeout).
14:41 UTC: p95 authorization latency falls to 620 ms; checkout success improves to 95.8 percent.
14:46 UTC: Provider support confirms partial processing degradation in primary region due to upstream network incident.
14:50 UTC: Additional traffic shifted to secondary provider where compliance and merchant rules allowed.
14:55 UTC: p95 latency falls below 500 ms; timeout rate under 1.2 percent.
15:02 UTC: Recovery criteria met. Incident status changed to mitigated.
15:20 UTC: Post-incident verification shows no duplicate capture anomalies and no settlement gaps.

## Root Cause
Primary root cause was degraded response time in the external primary payment processor endpoint serving authorization requests for the us-east merchant profile. This increased provider roundtrip latency significantly without immediate hard failures, which delayed detection by static error-rate thresholds. A contributing cause was retry amplification across service boundaries: order-service retried failed authorizations with aggressive timing while api-gateway also retried upstream timeouts, effectively multiplying load on payment-service and further increasing queueing delay. Another contributing factor was insufficient dynamic routing automation; failover to the secondary provider existed but required manual activation and method-specific allowlists, adding approximately 17 minutes from detection to broad traffic diversion. Internal payment-service compute capacity was not the primary cause, but saturation occurred secondarily once request volume rose. No code regression was identified in the deployment history during the incident window.

## Impact
- Customer impact: checkout delays and intermittent failures during a 55-minute period.
- Business impact: estimated conversion drop of 6.4 percent for affected cohorts during peak incident window.
- Operational impact: elevated ticket volume to customer support and manual incident coordination across payments, edge, and commerce teams.
- Technical impact:
  - p95 authorization latency peaked at 1.18 seconds.
  - Timeout-related failures reached 7.6 percent at peak.
  - Checkout completion fell to low of 91.9 percent.
  - Queue backlog for payment events rose but cleared within 25 minutes after mitigation.
- Data integrity: no confirmed duplicate charges, no irreversible transaction inconsistencies found after audit queries.

## Mitigation
Immediate mitigations focused on reducing customer-facing latency and preventing overload loops.
1. Enabled secondary provider routing for all eligible payment methods and card groups under existing contractual constraints.
2. Tuned retry behavior in api-gateway and order-service to reduce multiplicative traffic amplification.
3. Scaled payment-service workers and connection pools to handle backlog while failover took effect.
4. Increased monitoring granularity for provider roundtrip metrics and enabled temporary high-frequency alert evaluation.
5. Maintained finance safety controls to detect duplicate authorization or capture anomalies during failover.

Follow-up remediation items were created:
- Implement automatic provider failover based on latency/error composite SLO breach with hysteresis.
- Centralize retry budget policy so only one layer performs retries for payment authorization paths.
- Add anomaly detection alert for rising provider latency even when hard error rate remains low.
- Expand synthetic transaction probes across all provider regions every minute.
- Pre-approve broader method eligibility for secondary provider where risk controls permit.

## Lessons Learned
1. Latency-only provider degradation can produce major customer harm before static error thresholds trigger critical alerts. Composite alerting should combine latency and conversion impact.
2. Independent retries across gateway and business service layers can unintentionally cause traffic multiplication. A shared retry budget must be enforced across the request path.
3. Manual failover procedures are operationally safe but too slow for high-volume checkout events. Automation with guardrails is required.
4. Incident communications improved once timeline ownership moved to a dedicated incident commander; early assignment should be default for all payment path incidents.
5. Existing idempotency controls were effective and prevented financial integrity breaches despite elevated retries; this control should remain non-negotiable in all future refactors.
6. OpsCopilot correlation between gateway retries and provider latency helped shorten diagnosis time; additional dependency intelligence should be added for faster containment recommendations.
7. Recovery validation must include both service metrics and finance integrity checks; successful latency recovery alone is insufficient closure criteria for payments.

