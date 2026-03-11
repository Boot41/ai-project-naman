# Search Service Runbook

## Service Description
search-service provides full-text and faceted search across product catalog and order history indexes. It receives queries from api-gateway, enriches requests with user permissions from auth-service and user-service context, and executes against a distributed search cluster. The service supports autocomplete, relevance-ranked results, and filtered navigation used by customer and operations interfaces. It maintains ingestion pipelines from inventory-service and order-service events to keep indexes fresh. search-service is business-critical because search failures reduce conversion and increase support load, but partial degradation can be tolerated briefly with fallback behavior. SLO targets are p95 query latency below 280 ms, search success rate above 99.5 percent, and index freshness lag below 120 seconds for high-priority catalogs.

## Common Failure Modes
1. Search cluster shard imbalance. Uneven shard placement or hot partitioning causes high tail latency and partial timeouts.
2. Index ingestion backlog. Event consumer lag from inventory/order updates leads to stale or missing results.
3. Query explosion from malformed client requests. Unbounded wildcard or deep pagination triggers CPU spikes.
4. Cache invalidation bug. Stale query cache returns outdated inventory states or recently removed items.
5. Mapping/schema mismatch after index template change. New documents fail indexing due to field type conflicts.
6. Node-level memory pressure and garbage collection pauses on search workers.
7. Dependency timeout for auth or user context enrichment causing query rejection before search execution.
8. DNS/network partition between search-service API pods and underlying search cluster nodes.

## Important Metrics
- Query throughput by endpoint (`search_rps`, `autocomplete_rps`).
- Query latency percentiles and timeout rate.
- Success/error rate by query type and HTTP status.
- Search cluster health (`cluster_status`, shard allocation, unassigned shard count).
- Node resource metrics (CPU, heap usage, GC pause time, disk I/O).
- Cache metrics (hit ratio, eviction count, stale response count).
- Indexing pipeline metrics (ingest events/sec, lag seconds, failed indexing count).
- Freshness indicators (`index_freshness_seconds` by dataset).
- Slow query logs: top N expensive queries and cardinality-heavy filters.
- Upstream dependency metrics for auth/user enrichment latency.

## Investigation Steps
1. Clarify incident shape: complete outage, high latency, stale results, or partial query failures.
2. Check search-service golden signals and identify first anomaly timestamp.
3. Compare API-layer errors to cluster-layer health. A healthy API with red cluster usually indicates backend index/search node problem.
4. Inspect query latency distribution by endpoint and tenant segment. Tail-only degradation often points to shard hotspots.
5. Review unassigned shard count and recent cluster rebalance events. Sudden relocation can degrade performance.
6. Check ingest lag for inventory and order event streams. If freshness lag is high, verify consumer health and queue backlog.
7. Pull slow query samples and identify abuse patterns (wildcards, very broad filters, deep pagination).
8. Validate recent deploys: query parser changes, relevance model updates, index template/mapping modifications.
9. Confirm dependency behavior for auth/user enrichment calls. Upstream latency can appear as search latency.
10. Test known deterministic queries against both API endpoint and direct cluster query to separate service-layer and cluster-layer issues.
11. Check node-level memory and GC pressure; long GC pauses often align with timeout spikes.
12. Validate DNS resolution and network path between service pods and cluster endpoints.
13. Build a concise evidence timeline and choose containment path (traffic shaping, query guardrails, cluster recovery).

## Recovery Steps
1. If shard imbalance is primary, trigger controlled rebalance and temporarily reduce replica movement concurrency.
2. If cluster health is red/yellow due to node loss, restore failed node or promote replicas and reroute traffic.
3. If ingest backlog is high, scale consumers and prioritize critical index topics before non-critical analytics feeds.
4. If query explosion occurs, enable emergency query guardrails: wildcard restrictions, pagination caps, and per-client rate limits.
5. If mapping mismatch caused indexing failures, revert template or deploy compatible mapping migration; reindex failed documents.
6. If GC/memory pressure persists, reduce query concurrency and scale out search nodes with tuned heap settings.
7. If dependency enrichment path fails, enable degraded mode where non-critical personalization is skipped but core results remain available.
8. If cache serves stale data, flush selective keys and re-enable invalidation hooks.
9. Roll back recent query-parser or relevance deployment if correlated with incident onset.
10. Validate recovery through synthetic search probes, freshness lag reduction, and p95/p99 latency normalization over 30 minutes.

## Escalation Contacts
- Primary On-Call: Search Platform Engineer (`search-primary`).
- Secondary On-Call: Data Retrieval Reliability Engineer (`search-secondary`).
- Cluster Escalation: Search Infrastructure Specialist for shard allocation and node replacement.
- Dependency Escalations:
  - inventory-service event lag: Inventory Platform On-Call.
  - order-service event lag: Commerce Data On-Call.
  - auth enrichment failures: Identity On-Call.
- Incident Commander: Required for SEV1 and for SEV2 incidents affecting core search for more than 20 minutes.
- Escalation Triggers:
  - Search success rate below 92 percent for 10 minutes.
  - p99 query latency above 2 seconds for critical customer search routes.
  - Cluster status red with unassigned primary shards.
  - Index freshness lag above 15 minutes for top-selling catalog partitions.
- Vendor Escalation:
  - Managed search provider support ticket if cluster recovery actions fail or repeat node failure occurs within 24 hours.

