# Kafka replay and offset recovery

First preserve the incident timeline, consumer group, topic/partition, last successful
commit and original event IDs. Stop producers if a schema/policy defect is still producing
bad events. Retain original manifests and DLQ messages privately; do not log their bodies.

The consumer commits offsets synchronously after durable processing (or confirmed DLQ
delivery). `processed_events.event_id` is the replay guard. A database commit followed
by a failed Kafka commit is expected to deliver again; it must not create new features,
scores, alerts or audit records. Do not delete replay guards to force reprocessing.

For deliberate offset resets:

1. Stop **all** consumers in the affected group and verify it is inactive.
2. Capture source row counts, offset ranges and lag coverage. Confirm Kafka retention
   still contains the needed records. Save an offset export before changing the group.
3. Preview a reset with `kafka-consumer-groups.sh --reset-offsets --to-earliest --dry-run`
   plus the correct bootstrap server, group and `--topic transactions.v1` arguments.
4. Review the range, then repeat with `--execute` in the approved maintenance context.
5. Restart consumers, verify duplicate counters increase, committed lag returns to zero
   with fresh known-partition coverage, and all persisted row counts/fingerprints remain
   unchanged. Watch error/DLQ rates; zero or unknown lag alone is not proof of recovery.

For a non-destructive delivery replay, use the same generated manifest:

```sh
python scripts/run_load_test.py --mode kafka --replay --manifest .local/load-events.jsonl --report .local/replay.json
```

Re-publishing is distinct from resetting offsets. Keep event_id and transaction_id
unchanged; regenerating IDs exercises new ingestion, not deduplication. The original
manifest includes event timestamps, so replay alert timing is deliberately not assessed.

The automated disposable drill below resets the real broker group, requires observed
duplicate completions for every previously processed event, and compares all six data
tables plus migration/index fingerprints. Its project name and default loopback port
checks prevent using it as a general production reset tool:

```sh
python scripts/run_recovery_drill.py --project drill-ci --output .local/recovery
```

PostgreSQL connection/pool outages exhaust bounded retries and exit **without** DLQ or
offset commit; supervision restarts the worker and replays. Permanent validation and
other exhausted processing errors still reach the DLQ. If a DLQ publish fails, offsets
remain uncommitted. Fix the cause before replaying DLQ data; the encoded payload is
sensitive data and must never be copied into logs. A new model re-score is a separate
versioned backfill, not deletion of idempotency records.
