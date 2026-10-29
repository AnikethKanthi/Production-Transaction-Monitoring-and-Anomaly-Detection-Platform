# Logs and Prometheus

Run `docker compose up --build -d` to include Prometheus, then open
`http://127.0.0.1:9090/targets`. Both `api` and `worker` targets should be UP.
The configuration scrapes every 15 seconds, using API `/metrics/prometheus` on internal
port 8000 and worker `/metrics` on internal port 9101. The existing JSON dashboard
`/metrics` API is independent. `PROMETHEUS_PORT` and `WORKER_METRICS_PORT` change host
port bindings; the worker always listens on 9101 inside Compose.

Prometheus is a local development service with ephemeral storage. Configure persistent
storage and retention separately for production. Run one API process per container:
Python collector state is process-local, and multi-process deployment needs an explicit
Prometheus multiprocess configuration rather than multiple Uvicorn workers sharing a port.

## Metrics and example PromQL

| Signal | Query |
| --- | --- |
| API requests/second | `sum(rate(api_http_requests_total[5m]))` |
| API server error fraction | `sum(rate(api_http_requests_total{status_code=~"5.."}[5m])) / clamp_min(sum(rate(api_http_requests_total[5m])), 0.000001)` |
| API client errors/second | `sum(rate(api_http_requests_total{status_code=~"4.."}[5m]))` |
| API p95 latency | `histogram_quantile(0.95, sum by (le) (rate(api_http_request_duration_seconds_bucket[5m])))` |
| Persisted worker transactions/second | `sum(rate(worker_transaction_events_total{outcome="processed"}[5m]))` |
| Duplicates/second | `sum(rate(worker_transaction_events_total{outcome="duplicate"}[5m]))` |
| Rejected events/second | `sum(rate(worker_transaction_events_total{outcome=~"rejected|dead_lettered"}[5m]))` |
| Failed processing attempts/second | `rate(worker_processing_failures_total[5m])` |
| Worker message p95 duration | `histogram_quantile(0.95, sum by (le) (rate(worker_message_duration_seconds_bucket[5m])))` |
| Inference p95 duration | `histogram_quantile(0.95, sum by (le) (rate(transaction_anomaly_inference_duration_seconds_bucket[5m])))` |
| Fallback inference/second | `rate(transaction_anomaly_inference_total{status="fallback"}[5m])` |
| Kafka committed consumer lag | `worker_kafka_consumer_lag` |
| Kafka lag measurement age | `time() - worker_kafka_statistics_timestamp_seconds` |

Worker throughput increments after synchronous offset commit, so commit/DLQ failures do
not look like successfully completed messages. Processing failures count attempts including
retries. A `processed` count may include a database duplicate if an injected custom processor
does not return the standard `duplicate` result; the production processor does return it.
Message latency includes validation, processing, retries, and commit. Inference latency
measures model scoring/fallback only; all duration units are seconds.

Kafka statistics arrive via librdkafka callbacks every 10 seconds while polling. Lag sums
`max(hi_offset - committed_offset, 0)` for known, nonnegative partition offsets on
`transactions.v1`. Unknown offsets and the synthetic -1 partition are excluded. Check
`worker_kafka_lag_known_partitions` and statistics freshness before interpreting zero lag:
zero known partitions means unavailable coverage, not a caught-up consumer. This reports
the local consumer's known partitions, not an external inventory of every group partition.

## Label budget

API labels are method (fixed allowlist, otherwise OTHER), matched route template (otherwise
unmatched), and response status. Raw URLs, IDs, query strings, IPs, account/customer IDs,
and exception messages never become labels. API latency labels exclude response status.
Prometheus scrape requests are excluded from API traffic metrics. Worker outcomes are the
fixed processed/duplicate/rejected/dead_lettered set. Inference uses only scored/fallback;
model versions are now logged instead of labeled. Kafka lag is aggregated with no client,
topic, group, partition, or event-ID labels. Existing inference metric names are preserved,
but consumers should remove model-version selectors from their queries.

## Tracing transactions in JSON logs

API and worker Python logs are newline-delimited JSON with UTC timestamp, service, level,
logger, and message. Exceptions are escaped within the JSON record. The API accepts a
bounded ASCII `X-Correlation-ID` (`A-Za-z0-9._-`, maximum 128 characters), replaces invalid
or missing values with a generated ID, echoes the ID on normal/handled-error responses,
and isolates it with context variables across concurrent requests. Unhandled errors are
logged and counted as 500 before propagating to FastAPI's outer error handler; that outer
handler's response may lack the correlation header, but the error log retains the ID.

Transaction create/read service logs add `transaction_id`. Kafka event envelopes optionally
carry `correlation_id`; producers also put it in `x-correlation-id` Kafka headers and log
event/transaction IDs on successful delivery. Existing v1 events remain valid: missing
correlation falls back to the event ID. Consumer scope supplies correlation/event/transaction
IDs automatically to downstream processing, inference, alert, retry, and failure logs,
then clears the context before handling another event. Malformed events have no trusted
identity; rejected-event logs identify Kafka topic, partition, and offset.

The HTTP transaction API currently writes directly to PostgreSQL and does not publish a
Kafka event. Trace that path by HTTP correlation ID and transaction ID. For externally
published events, pass the originating correlation ID in the envelope and use producer and
consumer logs to follow the same event. This instrumentation does not add a new ingestion
or HTTP-to-Kafka bridge. Business-stage success messages occur inside the transaction;
the final consumer completion log confirms processing and offset commit succeeded.
