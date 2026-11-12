# Grafana dashboards and operational alerts

Start the stack with `docker compose up --build -d`. Compose finishes the database
migrations, including the ingestion timestamp index, before it starts the API. Open Grafana at
<http://127.0.0.1:3000>; credentials come from `GRAFANA_ADMIN_USER` and
`GRAFANA_ADMIN_PASSWORD` in `.env.example`. Grafana persists its state in
`grafana_data`. Changing the password variable does not reset an existing volume's
administrator password.

The provisioned Prometheus datasource has stable UID `prometheus`. The Transaction
Monitoring folder automatically contains Platform health, Transaction monitoring,
and Anomaly detection. Edit dashboard JSON in `observability/grafana/dashboards`;
Grafana reloads it within 30 seconds. Datasource/provider changes require restart.
The setup follows [Grafana file provisioning](https://grafana.com/docs/grafana/latest/administration/provisioning/).

## Definitions and scope

API request rate, 5xx fraction, and p95 latency use five-minute Prometheus rates.
Both scrape endpoints are excluded; health probes remain included. Histograms use
seconds. Worker throughput counts durable Kafka outcomes after offset commit.
Inference p95 includes both model and fallback paths; the outcomes panel separates them.

`/metrics/business` executes bounded-time queries every 15 seconds. Its health signal
means database connection and all three business queries succeeded, including schema
availability; API liveness alone does not prove database readiness. Query errors produce
`platform_database_up=0` and omit business metrics. An unreachable API instead triggers
BusinessMetricsUnavailable. Connection establishment may take up to ten seconds;
queries have individual two-second statement timeouts. A scrape exceeding ten seconds
also triggers BusinessMetricsUnavailable. This is application database reachability,
not PostgreSQL CPU, disk, replication, or connection-pool saturation monitoring.

Business gauges are persisted rows **created in the trailing five minutes**, including
the boundary, using UTC ingestion time rather than transaction occurrence time. They
are overlapping windows: do not sum samples or apply `rate()` to them. Transaction
volume includes both direct API and Kafka ingestion. Decline rate is `failed / all
transactions`, including pending/refunded in the denominator. Anomaly rate is positive
scores divided by successfully model-scored records, excluding fallback; it is distinct
from crossing the versioned alert threshold. Alert volume counts alert records created
in that window by severity, regardless of current investigation status. Alerts are
queried separately from transactions/anomalies to avoid multiplying counts.

Only fixed statuses/severities are labels. No IDs, model versions, accounts, countries,
or devices enter these metrics. The supplied PromQL assumes the single API business
scraper in Compose. When scaling API replicas, scrape this shared-database snapshot
once, rather than summing duplicate snapshots from each replica.

## Rules and first response

All rules evaluate every 15 seconds. The duration below is continuous breach time
after the measurement condition becomes true. Thresholds are initial local defaults;
review against production traffic and service objectives before deployment.

| Rule | Condition / hold | Response |
| --- | --- | --- |
| APIUnavailable | API scrape down / 1m | Check API logs, process and network. |
| APIErrorSpike | 5xx >5%, total >0.1 requests/sec / 2m | Inspect correlated errors, dependencies, recent releases. |
| APIHighLatency | Five-minute p95 >1s / 5m | Inspect slow routes, database and resource contention. |
| KafkaConsumerLag | >1,000 committed-offset lag, known partitions, sample age <60s / 5m | Check worker capacity, retries and broker connectivity. |
| KafkaLagUnavailable | Worker up, statistics stale >60s or unknown/absent coverage / 5m | Inspect group assignment and statistics callback; zero lag is not proof of health. |
| WorkerUnavailable | Worker scrape down / 1m | Check worker exit logs and Kafka/database connectivity. |
| WorkerFailures | >5 failed attempts in five minutes / 2m | Inspect retry causes and DLQ; attempts include retries. |
| NoIncomingTransactions | Zero rows ingested in five minutes, database healthy / 10m | Check upstream producers. Assumes continuous traffic; disable/schedule for quiet workloads. |
| DatabaseConnectionFailure | Business query/connection fails / 1m | Check PostgreSQL, credentials, pool and migration state. |
| BusinessMetricsUnavailable | Business scrape down / 1m | Check API reachability and scrape/query timeouts. |
| AnomalySpike | >20% positive scores with at least 20 scored records in five minutes / 5m | Review model/data changes and suspicious cohorts. |

Kafka lag covers the local worker's known partitions, not a broker-wide inventory.
Anomaly spikes use an absolute threshold, not a historical baseline. An API 5xx spike
and dependency alerts can fire together; no inhibition is configured.

Rules are **Prometheus-managed**, loaded automatically through `rule_files` and shown
in the dashboard's operational-alerts panel and <http://127.0.0.1:9090/alerts>.
No email, Slack, paging, contact point, or Alertmanager delivery is configured.

## Repeatable validation

From the repository root:

```sh
docker compose config --quiet
docker run --rm --entrypoint promtool -v "$PWD/observability/prometheus:/rules" -w /rules prom/prometheus:v3.2.1 check rules alert-rules.yml
docker run --rm --entrypoint promtool -v "$PWD/observability/prometheus:/rules" -w /rules prom/prometheus:v3.2.1 test rules alert-rules.test.yml
python scripts/check_monitoring.py --promtool /path/to/promtool
```

Promtool tests simulate each failure, verify no immediate firing before the hold,
verify firing, then verify resolution after the input disappears. Healthy, low-volume,
stale-lag and database-failure suppression cases guard against false alarms. The tool
evaluates the actual PromQL, following [Prometheus rule unit testing](https://prometheus.io/docs/prometheus/latest/configuration/unit_testing_rules/).
CI runs those tests and validates all dashboard expressions. API unit tests compare
snapshot values with known database fixtures and verify failure values are omitted.

For a live check in a disposable development stack: inspect `/targets`, dashboard
panels, and `/alerts`; stop the worker for over one minute to fire WorkerUnavailable,
restart it and confirm recovery. Stop PostgreSQL to trigger the database or business
scrape alert, then restart and confirm recovery. Do not run fault injection against
shared environments. No external notification delivery is implied by these tests.
