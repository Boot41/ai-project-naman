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

## Additional Postmortem Analysis Pack

## Expanded Causal Chain
- Trigger event: identify the first measurable technical anomaly.
- Amplifier: identify the mechanism that expanded impact (retries, queueing, resource contention, or control-plane instability).
- Customer symptom: map technical failure to user-visible behavior.
- Containment gate: describe the earliest decision that reduced further blast radius.
- Recovery gate: define the point where metrics stabilized and regression risk dropped.

## Counterfactual Assessment
1. If the first mitigation had been applied 10 minutes earlier, estimate impact reduction by KPI.
2. If retry budgets were centrally enforced, estimate reduced load multiplier.
3. If dependency health had weighted latency and error jointly, estimate earlier detection minute.
4. If failover had been automated with guardrails, estimate restoration acceleration.

## Detection Quality Review
- Signal lead time: minutes from first anomaly to first alert.
- Signal precision: false positives seen in similar windows.
- Correlation quality: whether dependency linkage was visible without manual deep-dive.
- Alert actionability: whether runbook points directly to containment path.

## Operational Impact Addendum
- Support and incident coordination load per team.
- On-call fatigue indicators (handoff count, bridge duration, action churn).
- Data correction workload after incident closure.
- Deferred engineering work caused by incident response diversion.

## Mitigation Effectiveness Scoring
- Containment speed score (time to halt blast radius growth).
- Stability score (time to return p95/p99 and error rates near baseline).
- Integrity score (whether financial/security/data correctness remained intact).
- Reversion risk score (likelihood of recurrence within 7 days).

## Action Register (Detailed)
- Detection improvements:
  - Add anomaly detectors for dependency latency variance.
  - Add route-level burn-rate alerts for top revenue flows.
- Containment improvements:
  - Create one-click degraded-mode profiles with pre-approved safety limits.
  - Centralize retry budgets and timeout inheritance policy.
- Recovery improvements:
  - Automate post-recovery validation checks for KPI + integrity metrics.
  - Add backpressure protections for async consumers during catch-up.
- Learning improvements:
  - Schedule game-day replay using incident timeline and synthetic load.
  - Convert key manual diagnosis steps into scripted diagnostics.

## Verification Checklist Before Closure
- Core user journey KPIs meet baseline threshold for sustained window.
- No hidden backlog above normal variance.
- No temporary override without owner and expiration.
- Follow-up actions tracked and acknowledged by owning teams.


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
