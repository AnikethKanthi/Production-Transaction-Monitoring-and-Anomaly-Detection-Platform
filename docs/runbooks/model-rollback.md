# Model rollback

Record current model/metadata/threshold hashes, fallback rate, scoring latency and alert
volume first. Preserve the failing artifact privately. Select a previously evaluated,
trusted artifact bundle with matching feature definition/order and threshold SHA-256;
joblib is executable input and must never be loaded from an untrusted source.

Rebuild/redeploy the worker image with the known-good bundle under its configured
`/models` paths. The default Compose model paths are baked into its environment; changing
host-only MODEL_PATH does not replace a mounted/baked artifact. Review the image contents
and compatible threshold configuration together. Stop/restart the worker rather than
overwriting a model while it is scoring. No database downgrade is required for a model
rollback unless the release includes a separately reviewed incompatible schema change.

Verify startup logs identify the intended model, new anomaly records use that version,
fallback metrics fall, inference latency is acceptable and qualifying probe transactions
produce alerts with the matching policy/threshold evidence. Check lag freshness and drain
after the restart. If the bundle cannot load, the worker stores explicit `fallback.v1`
scores and avoids model-based alerts; fallback is degraded service, not recovery proof.

Existing anomaly/alert records retain their original versions. Kafka replay skips already
processed event IDs; it does not silently re-score historical rows. Any historical
re-evaluation needs a versioned backfill design that preserves prior evidence and operator
audit history. Document the affected time range and rollback reason in the incident record.
