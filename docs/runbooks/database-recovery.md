# Database backup and restore

Name the backup owner and agree on the RPO and RTO before deployment. A local Docker volume
is not a backup.
The included logical dump covers one database, not cluster roles, secrets, Kafka,
Redis, model artifacts or point-in-time recovery. Schedule encrypted off-host backups,
access controls, retention, checksums and routine restore drills separately; use WAL
archival/PITR when the required RPO is shorter than the logical-backup interval.

The disposable drill uses the PostgreSQL container's matching-version pg_dump and
pg_restore tools. It quiesces API/worker writers, fingerprints rows and index definitions,
takes a custom-format dump, and confirms the source did not change. It creates a fresh
random `recovery_<uuid>` database, restores with `--exit-on-error --single-transaction`,
and compares every application table and migration version. Only the scratch database
it created is dropped. API/worker are restarted even when restore fails. Dumps remain
under ignored `.local/` and require private/encrypted storage and cleanup after review.

```sh
docker compose -p drill-ci up --build -d --wait api worker
python scripts/run_recovery_drill.py --project drill-ci --output .local/recovery
```

Use a fresh disposable `drill-*` stack on default loopback ports, with host dependencies
installed and matching POSTGRES_* credentials. The script interrupts Kafka/PostgreSQL
as well as testing backup/restore; never repoint it at a shared database or project.
The JSON report records verification flags, elapsed times and archive SHA-256. A failed
or missing report is not a successful restore. Local control-flow tests do not substitute
for an actual PostgreSQL restore; current execution status is in the performance report.

For a real incident:

1. Stop/quiesce writers, preserve failing storage and establish the last valid backup.
   Do not destroy the source volume or restore over it as an initial recovery action.
2. Verify archive checksum/provenance, PostgreSQL tool compatibility, free disk space,
   target identity, required roles/extensions and model artifact availability.
3. Restore into a new isolated database. Never use `--clean` against a shared target.
   Verify row contents/counts, FK/unique/check constraints, indexes, migration version
   and representative reads before considering promotion.
4. Reconcile the restored processed_events guards with Kafka offsets. Events committed
   to Kafka after the backup snapshot may need replay from an earlier offset to avoid
   data loss; retained IDs prevent duplicates. Verify retention covers that range.
5. Rebuild/discard Redis rolling counters and caches as appropriate. They may describe
   transactions newer than the restored database. Reconcile operator audit changes
   separately; Kafka ingestion replay cannot reconstruct later human decisions.
6. Promote only after verification, reconnect API/workers with bounded pools and monitor
   latency, lag, errors and new transaction/alert creation. Record measured RTO, actual
   data-loss window and any unrecoverable events in the incident report.
