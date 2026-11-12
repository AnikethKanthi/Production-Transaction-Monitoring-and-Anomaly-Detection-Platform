# Model rollback

Before changing anything, record the current model, metadata, and threshold hashes along
with the fallback rate, scoring latency, and alert volume. Keep the failing artifact in a
private location for later analysis. Roll back only to a trusted, previously evaluated bundle
whose feature order and threshold SHA-256 match. A joblib file contains executable input, so
never load one from an untrusted source.

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
