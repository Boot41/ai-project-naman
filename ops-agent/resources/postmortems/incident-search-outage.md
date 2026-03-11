# Incident Search Outage

## Incident Summary
On 2026-01-27, search-service experienced a major availability incident caused by shard allocation failure after a rolling infrastructure update in the search cluster. The outage began at 09:18 UTC when customer-facing search endpoints started returning 503 and timeout responses. The incident was declared SEV1 at 09:24 UTC because core catalog search functionality was effectively unavailable for most users. autocomplete degraded first, followed by full search route failures as cluster state moved from yellow to red and primary shards became unassigned. Partial service was restored by 09:52 UTC through traffic shaping and selective query degradation mode. Full recovery occurred at 10:21 UTC after node restoration, shard reallocation stabilization, and replay of lagging index ingestion streams. The event highlighted operational fragility in cluster rollout sequencing and insufficient preflight shard-capacity checks.

## Timeline
09:12 UTC: Search infrastructure rollout begins to patch underlying nodes in one availability zone.
09:16 UTC: Cluster rebalance activity increases; shard relocation queue grows but remains below warning threshold.
09:18 UTC: First customer impact observed. `search_success_rate` drops below 97 percent.
09:20 UTC: Autocomplete timeout alerts trigger. Search on-call acknowledges and opens triage bridge.
09:22 UTC: Cluster health transitions to red; unassigned primary shards detected for top catalog indexes.
09:24 UTC: Incident classified SEV1 due to widespread search unavailability.
09:26 UTC: api-gateway error rate rises for `/search/query` routes. OpsCopilot links outage to shard allocation failures.
09:29 UTC: Decision made to halt rollout and freeze index template changes.
09:31 UTC: Degraded mode enabled in search-service to bypass personalization enrichment and reduce query complexity.
09:34 UTC: Query guardrails activated (wildcard restrictions, deep pagination disabled, tighter per-client limits).
09:38 UTC: Infrastructure team restores two recently drained nodes with high-shard density.
09:42 UTC: Primary shard assignment begins recovering; cluster remains red but improving.
09:46 UTC: Ingestion lag spikes due to paused consumers and backlog accumulation.
09:52 UTC: Service availability returns to partial with success rate above 90 percent; incident remains active.
10:01 UTC: Cluster transitions from red to yellow; unassigned primary shard count reaches zero.
10:08 UTC: Ingestion consumers scaled and backlog drain begins.
10:14 UTC: p95 query latency drops below 350 ms; timeout rate under 2 percent.
10:21 UTC: Recovery complete. Search success rate above 99 percent and freshness lag below 3 minutes.
10:45 UTC: Post-incident validation confirms index consistency for critical catalog partitions.

## Root Cause
The primary root cause was an unsafe sequence during search cluster node patching that temporarily reduced available shard capacity below the threshold required for primary shard assignment. The rollout drained nodes with disproportionate shard ownership before rebalancing completed, resulting in unassigned primaries for high-traffic catalog indexes. A secondary contributing factor was aggressive relocation concurrency, which increased cluster coordination load and delayed stable assignment. Another contributor was insufficient preflight validation: the rollout process did not enforce a hard check for shard skew and required free capacity prior to draining the next node. At the service layer, expensive query patterns worsened perceived outage by increasing pressure on remaining healthy nodes. No application code regression in search-service API handlers was found.

## Impact
- Customer impact: users experienced failed or empty search responses for catalog and order lookups during peak business window.
- Business impact: drop in product discovery and conversion; support channels saw rapid increase in “cannot find item” reports.
- Operational impact: cross-team emergency response involving Search Platform, Edge SRE, Commerce Data, and incident command.
- Technical impact:
  - Search success rate dropped to a low of 61 percent.
  - p99 latency exceeded 4.5 seconds at peak.
  - Unassigned primary shards affected top catalog indices.
  - Index freshness lag peaked at 28 minutes before backlog recovery.
- Data integrity: no permanent data loss; delayed indexing caused temporary stale results until replay completion.

## Mitigation
Response actions were prioritized to recover availability quickly while stabilizing cluster state.
1. Stopped infrastructure rollout immediately to prevent further capacity loss.
2. Restored drained high-density nodes and reduced relocation concurrency to lower cluster control-plane pressure.
3. Enabled search degraded mode to reduce dependency overhead and query execution cost.
4. Applied emergency query guardrails to block costly wildcard and deep pagination requests.
5. Scaled ingestion consumers after cluster stabilization to clear backlog and restore index freshness.
6. Coordinated gateway-side controls to reduce retries and avoid additional load amplification.

Remediation actions assigned after incident:
- Add mandatory preflight gate for shard skew, free capacity, and allocation simulation before each node drain.
- Implement progressive rollout policy with automatic rollback on red-cluster transition.
- Build canary index health checks tied to deployment pipeline.
- Introduce tiered index protection so critical catalog shards receive placement priority.
- Expand runbook guidance for degraded-mode activation thresholds and safe query guardrail defaults.

## Lessons Learned
1. Cluster maintenance procedures must be capacity-aware at shard level, not just node count level.
2. Red-cluster conditions should trigger immediate automated rollout halt without manual intervention.
3. Query guardrails are an effective containment tool and should be pre-staged with one-click activation.
4. Search freshness and search availability are separate health dimensions; both need explicit recovery criteria before closure.
5. Incident coordination improved once dependency teams received early, role-specific action requests; template-driven escalation should be standardized.
6. OpsCopilot dependency-chain reasoning accelerated diagnosis by highlighting the sequence from infrastructure rollout to shard failure to API errors.
7. Post-recovery validation must include index consistency checks for critical partitions before incident closure.
8. Engineering ownership boundaries between search API and search infrastructure were clear, but rollout safety ownership was fragmented; a single change owner is now required for cluster patch events.

