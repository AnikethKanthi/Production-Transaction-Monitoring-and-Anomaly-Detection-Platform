# Performance results and acceptance status

Measured 2026-11-06 on Windows 11, Python 3.14.6. The committed
[raw component report](component-baseline.json) records the model SHA-256, platform,
sample counts and timing distributions. Reproduce with:

```sh
python scripts/benchmark_components.py --report .local/component-performance.json
```

The run uses 2,000 deterministic SQLite rows, a single in-process ASGI client, ten
warmups and 200 measured samples. It executes the actual transaction filtering,
counting, ordering and serialization code. Authentication is explicitly overridden
only inside this standalone benchmark; no production bypass was introduced. Model
timings use the committed `isolation_forest.v1` artifact and one fixed feature vector.

| Local component | p50 | p95 | max |
| --- | --- | --- | --- |
| Filtered transaction list, SQLite + ASGI | 11.28 ms | 17.26 ms | 20.49 ms |
| Actual model inference including instrumentation | 30.92 ms | 37.16 ms | 48.32 ms |

These numbers exclude network, PostgreSQL, Redis authorization limits, Kafka, real
account histories and concurrent users. They are **not an end-to-end SLA result**.
The local environment has no Docker executable or running PostgreSQL/Redis/Kafka
stack, so live system load, query plans and pg_dump/pg_restore could not be executed.

| Target | Current evidence / status |
| --- | --- |
| Common API p95 <300 ms | Local query component is below the threshold. Live HTTP/PostgreSQL/Redis target remains unverified. The HTTP runner reports per-route p95 and fails on errors/429s as well as slow latency. |
| Qualifying alerts created <10s | Unverified on a live pipeline. Kafka load reports persisted alert timestamps relative to event production; zero alerts reports **not assessed**, never a pass. Synchronize clocks. |
| Event throughput / consumer lag | Live values unavailable. Kafka runner measures completed event IDs per wall-clock second and fresh known-partition lag, omitting unknown lag rather than showing zero. |
| No duplicate rows on replay | Real SQLite persistence test passes for all six event-related tables after a database-success/Kafka-commit-failure replay. Actual broker offset-reset drill is configured but not run locally. |
| Recovery after Kafka/PostgreSQL interruption | Injected worker failures pass: transient Kafka polling resumes; exhausted transient DB errors leave offsets uncommitted for supervised replay. Live interruption drill remains unverified. |
| Database backup and restore | Safety/control-flow tests pass, including failed restore cleanup. Actual PostgreSQL restore and data/index fingerprints remain unverified locally. |

The new CI recovery job starts an isolated `drill-ci` stack, produces live HTTP and
pipeline reports, resets offsets, interrupts dependencies, restores a custom-format
backup into a new scratch database and compares fingerprints. It uploads only result
JSON, excluding credentials, event manifests and database dumps. CI has **not** run
these unpushed changes; no remote success is claimed.

## Tuning decisions

- API pool: five persistent connections plus at most five overflow; synchronous worker:
  one persistent connection and zero overflow. Both use three-second acquisition,
  five-minute recycling, pre-ping and LIFO reuse. Capacity is bounded: one API process
  plus one worker can use at most eleven application connections, before migration,
  monitoring/backup clients and operational reserve. Multiply by processes/replicas.
  These are initial budgets, not a demonstrated optimum. See
  [SQLAlchemy pooling](https://docs.sqlalchemy.org/en/20/core/pooling.html).
- Migration `0009` extends the status/time index with the UUID tie breaker, adds
  currency/time/UUID for the common currency filter, and adds status/creation/UUID
  for the alert queue. The existing account/time history index is retained. Query-plan
  evidence must be captured on representative PostgreSQL data before claiming a speedup.
  Index creation here is blocking; deploy in a maintenance window for large tables.
- Batch seeding uses executemany in independently committed batches of 250, adjustable
  to 1–1,000, with deterministic IDs and conflict-ignore reruns. This removes per-row
  commits for offline fixture ingestion. Kafka publishing batches buffered records
  and flushes once rather than once per record.
- Live worker database transactions remain per event. Features depend on previously
  committed customer history, alerts have FK/audit ordering, and Kafka commits must
  follow durable storage. Cross-event batching would need an explicit ordering and
  failure-isolation design; it is not enabled without evidence that its tradeoff helps.
- Customer history currently grows without a fixed bound, count-based pagination still
  counts matching rows, substring search can scan, and deep offsets can be expensive.
  These remain likely scale limits. Profile real plans/history distributions before
  adding more indexes, approximate counts, keyset pagination or history summaries.

## Live measurement commands

Use a disposable stack with credentials from the security runbook. API mode directly
creates records and requires an administrator for mixed/write runs. It does not publish
Kafka events, so alert timing belongs to Kafka mode. Install the API development and
worker packages in the host environment. Run commands from the repository root:

```sh
python scripts/run_load_test.py --mode api --operation mixed --count 100 --rate 10 --concurrency 5 --token-file .local/admin.token --report .local/api-load.json
python scripts/run_load_test.py --mode kafka --count 100 --manifest .local/load-events.jsonl --report .local/pipeline-load.json
python scripts/run_load_test.py --mode kafka --replay --manifest .local/load-events.jsonl --report .local/republish.json
python scripts/seed_database.py --count 10000 --batch-size 250
python scripts/explain_queries.py --refresh-statistics --report .local/query-plans.json
```

Use the same dataset/configuration and warmup when comparing runs. Record resources,
replicas, data size, offered rate and rate-limit settings. The HTTP runner has a bounded
queue and reports achieved rate; saturation can reduce achieved load. Increase limits
explicitly in the disposable stack for higher-rate tests; never count 429s as a good
latency result. Kafka mode publishes a burst; `--rate` controls HTTP mode only. Scoring
latency comes from persisted anomaly records, not a guessed model-time estimate.

HTTP/pipeline runners return nonzero on failed assessed targets. Re-publishing a manifest
preserves IDs/bytes, but existing rows alone do not prove broker replay completed. Use
the offset/duplicate-counter recovery drill for that evidence. A backup is not verified
until it restores: [PostgreSQL pg_dump](https://www.postgresql.org/docs/17/app-pgdump.html)
and [pg_restore](https://www.postgresql.org/docs/17/app-pgrestore.html) describe the formats.
