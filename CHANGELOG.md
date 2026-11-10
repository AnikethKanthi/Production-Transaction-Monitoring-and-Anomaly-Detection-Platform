# Changelog

## 1.0.0 — 2026-11-10

First stable release of the transaction monitoring reference platform.

### Included

- Authenticated FastAPI transaction, metrics, investigation, and audited alert-workflow APIs.
- Kafka `transaction.created` ingestion with validation, manual commits, retry, DLQ metadata, and replay idempotency.
- Versioned deterministic features, reproducible Isolation Forest training, evaluated threshold configuration, inference persistence, fallback behavior, and alert evidence.
- PostgreSQL migrations through `0009`, Redis rolling metrics/cache, structured correlation-aware logging, Prometheus metrics, provisioned Grafana dashboards, and operational alert rules.
- Responsive React operator console for dashboard, transaction investigation, alert queue, evidence review, assignment, acknowledgement, resolution, and false-positive closure.
- Performance tooling, backup/restore and interruption drills, end-to-end Compose/browser testing, contract tests, dependency audits, and container scanning.
- Complete architecture, API, event, database, ML, deployment, operator, incident, recovery, and rollback documentation.

### Operational notes

- The bundled model and threshold are evaluated on synthetic data and require monitoring and representative labeled data before regulated or high-stakes production use.
- Compose is a development, demonstration, and single-host reference deployment; production stateful services need managed durability, TLS, secret management, backup, and capacity planning.
- Release images are built only when Docker executes `scripts/build_release.py` or the tag workflow. Source does not claim image digests that were not built.
