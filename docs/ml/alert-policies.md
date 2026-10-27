# Deterministic anomaly alerts

The worker enables `anomaly_alert.v1` by loading `ALERT_THRESHOLD_PATH` at startup.
The threshold sidecar must identify `anomaly_threshold.v1`, the current feature version,
an inclusive comparator, no segment overrides, and the exact SHA-256 of the model artifact.
A missing, corrupt, or incompatible configuration disables model alerts and logs an error;
transaction persistence and fallback scoring continue. Restart the worker to load changes.

An alert requires a finite score with status `scored`, the configured model version,
and `score >= threshold`. Fallback scores never qualify. This task activates the previously
evaluated global threshold for alerts; the existing positive-score anomaly metrics remain
a separate definition and are not an alert-count metric.

| Severity | Inclusive lower bound | Exclusive upper bound |
| --- | --- | --- |
| Low | threshold | threshold + 0.025 |
| Medium | threshold + 0.025 | threshold + 0.05 |
| High | threshold + 0.05 | threshold + 0.10 |
| Critical | threshold + 0.10 | none |

Exactly one severity is selected. For the committed model the base threshold is
0.229602043777838. Bands are deterministic operational triage defaults, not calibrated
fraud probabilities or independently validated risk categories. Country, currency, device,
and payment-method values do not independently change severity in this policy.

Every alert stores transaction/event/anomaly IDs, severity, policy version, model version,
and a JSON evidence snapshot. Evidence includes the exact score, threshold configuration,
comparator, band boundaries, plain-language reasons, and the original inference features.
Features are observed context, not a causal explanation of Isolation Forest decisions.

Transaction, inference vector, score, alert, and processed-event receipt commit in one
database transaction. Event replay skips an existing receipt. A unique constraint on
`(transaction_id, policy_version)` and targeted `ON CONFLICT DO NOTHING` prevent repeated
or concurrent alert decisions from creating duplicate rows. A different policy version
can intentionally produce a new alert during an explicit future re-evaluation; this worker
does not automatically reprocess historical transactions. Storage failures roll back the
whole event so the existing consumer retry/dead-letter behavior remains effective.

Apply Alembic migration `0006` before running the worker. It creates the `alerts` table,
severity validation, foreign keys, deduplication constraint, and lookup indexes. Its downgrade
drops the alerts table. This implementation persists alerts locally; no external notifications
are sent.
