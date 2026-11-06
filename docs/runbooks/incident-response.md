# Incident response

Assign an incident lead and note UTC start time, affected services, correlation/event
IDs, deployment/model versions and first failing metric. Preserve logs without raw
payment payloads or credentials. Classify user impact before changing infrastructure.

| Symptom | Investigate | Contain / recover | Verify |
| --- | --- | --- | --- |
| API p95 >300 ms or errors | Per-route latency, 5xx vs 429, database plans/locks, pool wait, Redis | Reduce offered load, fix slow queries/dependency health, roll back the offending release if needed. Do not remove rate limits to conceal errors. | Authenticated reads/writes succeed; p95 and errors recover under the same load. |
| Worker throughput drops / lag grows | Lag freshness/partition coverage, Kafka connectivity, retries, database health, model latency | Recover the failing dependency. Transient DB failure leaves offsets uncommitted; Compose restarts the exited worker. Scale only with a connection budget and consistent per-customer ordering. | New probe events persist, offsets advance, fresh known lag drains and DLQ stays stable. |
| PostgreSQL unavailable | Container state, disk, connection counts/locks, credentials and pool saturation | Restore connectivity; use database recovery runbook for lost/corrupt storage. Do not delete volumes or replay guards. | New events persist exactly once after reconnection; audit evidence and constraints remain intact. |
| Kafka unavailable | Broker/controller health, storage, advertised listeners, group assignment | Restore broker and allow jittered polling/reconnect; retain producer manifests if delivery is uncertain. | Confirm delivery and committed offsets, then compare persisted IDs; unknown lag is not healthy lag. |
| Model fallback / anomaly spike | Artifact/metadata/threshold hashes, scoring status, inference duration, recent data changes | Restore a compatible trusted model; follow model rollback runbook. Do not disable alerts or lower thresholds merely to hide a spike. | New scores identify the intended model, fallback rate falls, qualifying alerts have evidence. |
| Redis unavailable | Socket errors and health, security limiter availability | Restore Redis. Protected API requests fail closed; worker counters remain best effort. Dashboard cache can fall back only after authentication protection is available. | Authenticated requests succeed, rolling metrics are available; caches/counters agree with their documented scope. |

Use [Kafka replay](kafka-replay.md), [database recovery](database-recovery.md),
[observability](observability.md), [operational alerts](operational-alerts.md) and
[security](security-resilience.md) for details. Model artifacts are trusted executable
inputs; do not load an unknown artifact during an incident.

Run `scripts/run_recovery_drill.py` only on a fresh disposable `drill-*` project; it
stops services, resets offsets and restores a scratch database. For real infrastructure,
use the reviewed incident-specific commands and verify the target before mutation.
Do not repeatedly restart services without identifying the failing dependency.

Close only after new end-to-end probe transactions succeed, freshness and queue drain
are verified, no duplicate rows appear, and affected time ranges are reconciled. Record
cause, containment, replay/restore boundaries, evidence, data loss, achieved RTO/RPO,
and follow-up owners. Performance/recovery results must state unexecuted checks explicitly.
