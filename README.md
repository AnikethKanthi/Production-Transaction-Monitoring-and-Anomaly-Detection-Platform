# Production Transaction Monitoring v1.0.0

A production-oriented reference platform that ingests transaction events through Kafka,
persists them exactly once, builds deterministic behavioral features, scores them with a
versioned Isolation Forest model, creates explainable alerts, and gives operators an audited
investigation workflow. The monorepo contains FastAPI, a standalone Python worker, React and
TypeScript, PostgreSQL, Redis, Kafka in KRaft mode, Prometheus, and Grafana.

```mermaid
flowchart LR
  P[Producer] --> K[Kafka] --> W[Feature + model worker] --> D[(PostgreSQL)]
  W --> A[Alert policy]
  U[Operator UI] --> API[FastAPI] --> D
  API --> U
```

Business APIs have no default credentials. Tokens are opaque, per-user, and stored only as
SHA-256 hashes by the service. See [security](docs/runbooks/security-resilience.md) before
using the project beyond a disposable local environment.

## Prerequisites

- Git, Docker Desktop with Linux containers and Docker Compose v2
- At least 4 GB available memory and ports 5173, 8000, 9092, 5432, and 6379 available
- Python 3.12+ for setup, smoke tests, event publishing, and the guided demo
- Node.js 22.12+ only when developing or testing the frontend outside Docker

## Quick start with Docker

From the repository root, create a disposable operator. PowerShell:

```powershell
python scripts/create_auth_user.py --username local-operator --role operator --token-file .local/operator.token > .local/operator.json
$identity = Get-Content .local/operator.json | ConvertFrom-Json
$env:AUTH_USERS = ConvertTo-Json -Compress -InputObject @($identity)
docker compose config --quiet
docker compose up --build -d --wait --wait-timeout 240
python scripts/smoke_test.py
python scripts/check_contracts.py
```

POSIX shell:

```sh
python scripts/create_auth_user.py --username local-operator --role operator --token-file .local/operator.token > .local/operator.json
export AUTH_USERS="$(python -c 'import json; print(json.dumps([json.load(open(".local/operator.json"))]))')"
docker compose config --quiet
docker compose up --build -d --wait --wait-timeout 240
python scripts/smoke_test.py
python scripts/check_contracts.py
```

Open <http://localhost:5173>, paste the value from `.local/operator.token`, and sign in.
The token and identity files are ignored by Git. Never paste tokens into commands, logs, or
committed configuration. Use an `administrator` identity only for direct transaction creation.

Compose runs a one-shot `migrate` service after PostgreSQL becomes healthy and waits
for migrations to complete before starting the API.

Infrastructure defaults work without an `.env` file, but protected business features require
the `AUTH_USERS` value created above. To customize ports or credentials, copy
`.env.example` to `.env` (`Copy-Item .env.example .env` in PowerShell, or
`cp .env.example .env` in a POSIX shell). Keep the local credentials out of production.

| Service | Local address |
| --- | --- |
| React application | http://localhost:5173 |
| API health | http://localhost:8000/health |
| API documentation | http://localhost:8000/docs |
| PostgreSQL | localhost:5432 |
| Redis | localhost:6379 |
| Kafka (host clients) | localhost:9092 |
| Kafka (Compose clients) | kafka:29092 |

`GET /health` returns `{"status":"ok","service":"api","version":"1.0.0"}`.
It checks API liveness. Compose independently checks PostgreSQL, Redis, Kafka, API,
and web health. Compose creates the `transactions.v1` topic before starting the API and
worker. The worker validates and persists each event with an idempotency receipt, retries
processing failures, and routes malformed or exhausted records to `transactions.v1.dlq`.
Kafka offsets are committed only after persistence or successful dead-letter publication.
Each accepted transaction also stores the deterministic `transaction_features.v1` inference
vector, including velocity, customer-baseline, location, device, IP, time, and payment signals.
The frontend checks the real API through a same-origin `/api` proxy.

```sh
docker compose ps
docker compose logs --tail=100
docker compose down
```

Named volumes preserve infrastructure data when containers stop. On later runs,
the existing PostgreSQL volume retains its original credentials. If a host port is
occupied, change its value in `.env`; pass the changed API/web URLs to the smoke script.

## Demonstrate ingestion through resolution

Install the worker package once so the host can publish Kafka events, then start an isolated
demo project:

```sh
python -m venv .venv
# PowerShell: .venv\Scripts\Activate.ps1
# POSIX: source .venv/bin/activate
python -m pip install -e "./apps/worker[dev]"
python scripts/demo.py start
```

The command builds a fresh stack, creates a private operator token, publishes deterministic
history plus a model-verified anomaly, and prints the transaction and alert IDs. Open the UI,
read the score, threshold, reasons, and observed features, then resolve the alert with an
investigation note. Finish with:

```sh
python scripts/demo.py verify
python scripts/demo.py stop
```

Verification requires the persisted `create` and `resolve` audit entries. `stop` removes only
the uniquely named disposable demo project and its volumes. See the
[operator runbook](docs/runbooks/operator-investigation.md) for the complete workflow.

## Run applications without Docker

Use Python 3.12 or newer and Node.js 22.12 or newer. Create a virtual environment:

```sh
python -m venv .venv
```

Activate it with `.venv\Scripts\Activate.ps1` on PowerShell or
`source .venv/bin/activate` on POSIX shells, then install both Python projects:

```sh
python -m pip install -e "./apps/api[dev]" -e "./apps/worker[dev]"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In separate terminals, start the worker with `python -m worker.main`, and the UI:

```sh
cd apps/web
npm ci
npm run dev
```

Publish generated events from the repository root while Kafka and the worker are running:

```sh
python scripts/generate_transactions.py --count 10 --interval 0.1
```

The v1 event contract is stored at
`contracts/events/transaction-created.v1.schema.json`. Kafka records use the transaction
UUID as their key, which keeps events for the same transaction in one partition.

## Train the anomaly model

The worker converts qualifying scores into deduplicated alerts with Low, Medium, High,
or Critical severity and evidence. See `docs/ml/alert-policies.md` for rules and activation.

Investigate alerts through `/alerts`: list/filter, inspect evidence, acknowledge, assign,
resolve, or mark false positives. Mutations require version checks and write audit history.
See `docs/api/alert-workflow.md` for request examples and state transitions.

Evaluate and tune the saved model with `python scripts/evaluate_threshold.py`.
The versioned threshold sidecar and report record held-out precision, recall, F1, alert
volume, error reviews, and segment candidates. See `docs/ml/threshold-strategy.md`.

Install the API ML dependencies and run the deterministic training command:

```sh
pip install -e "apps/api[ml]"
python scripts/train_model.py
```

The command uses seed `42` to generate labeled synthetic data and trains
`isolation_forest.v1` on normal examples. It writes the versioned joblib model, metadata,
evaluation report, and score-distribution chart to `model-artifacts/`. Generated CSV datasets
are written beneath `data/` and can be recreated with the same command.

The worker loads the active model at startup and stores one anomaly score, model version,
scoring status, and inference latency for every processed transaction. If loading or scoring
fails, processing continues with the explicit `fallback.v1` score. Prometheus inference
metrics are available from the worker on `http://127.0.0.1:9101/metrics` by default.

Dashboard aggregates are available at `GET /metrics` for a requested time range and hourly or
daily interval. `GET /metrics/rolling?window_minutes=60` serves Redis-backed minute buckets.
Both responses include volume, amount, average amount, outcome rates, anomaly rate, latency,
country breakdowns, and payment-method breakdowns. Database aggregate responses use a
short-lived Redis cache configured by `METRICS_CACHE_TTL_SECONDS`; rolling buckets use
`ROLLING_METRICS_TTL_SECONDS`.

The development UI proxies requests to `http://127.0.0.1:8000`. Set
`API_PROXY_TARGET` if the API runs at a different address. API liveness is independent
of the database, but repository operations require a migrated PostgreSQL database.

## Database migrations and tests

SQLAlchemy uses the psycopg driver and a lazily created connection pool with
`pool_pre_ping`. Outside Compose, connection settings come from the `POSTGRES_*`
variables in `.env` or an explicit `DATABASE_URL` override. Compose uses the internal
`postgres:5432` address and its own `POSTGRES_*` values. Passwords are safely URL-encoded.

From the root with the virtual environment active:

```sh
python -m alembic -c apps/api/alembic.ini upgrade head
python -m alembic -c apps/api/alembic.ini current
python -m alembic -c apps/api/alembic.ini check
```

`downgrade base` reverses the initial migration and **drops both tables and their data**.
The integration suite tests that operation only in disposable, randomly named schemas.

For PostgreSQL integration tests, explicitly set `TEST_DATABASE_URL` to a PostgreSQL
database where the test user can create schemas (the variable is read from the process
environment, not `.env`). In PowerShell:

```powershell
$env:TEST_DATABASE_URL = 'postgresql+psycopg://monitoring:local-development-only@127.0.0.1:5432/transactions'
python -m pytest apps/api/tests -W error
```

In POSIX shells, export the same variable before running pytest. Without this variable,
integration tests are skipped; the dedicated GitHub Actions database job always sets it.
Tests cover upgrade/downgrade/re-upgrade, schema drift, indexes, insert/retrieve,
constraint enforcement, and complete rollback on duplicate event IDs.
See [the data model](docs/architecture/data-model.md) for table definitions and usage.

## Validate

The React dashboard at `/` displays live metrics, transaction volume, status distribution,
and anomaly trends. Navigation links to Transactions and Alerts. See
`docs/runbooks/frontend-dashboard.md` for API configuration, query behavior, and UI tests.

Transaction search and sorting, URL-preserved filters, score/evidence details, and alert
acknowledge/assign/resolve actions are documented in `docs/runbooks/operator-investigation.md`.

Prometheus runs locally at `http://127.0.0.1:9090` and scrapes the API and worker.
Structured JSON logs include correlation IDs and transaction/event IDs. See
`docs/runbooks/observability.md` for metrics, PromQL queries, and tracing instructions.

From the root, using the active virtual environment:

```sh
python -m pytest apps/api/tests
python -m pytest apps/worker/tests
python -m ruff check apps/api apps/worker scripts/smoke_test.py
python -m ruff format --check apps/api apps/worker scripts/smoke_test.py
npm ci --prefix apps/web
npm run build --prefix apps/web
npx --prefix apps/web playwright install chromium
npm run test:e2e --prefix apps/web
docker compose build
```

GitHub Actions runs Python lint, formatting and tests, a locked frontend build,
container smoke tests, a real event-to-resolution workflow, dependency audits, contract
checks, and container scans. See [testing](docs/testing.md).

## Release

All direct Python and frontend dependencies are exactly pinned; npm transitive dependencies
and integrity hashes are committed in `package-lock.json`. Validate release metadata with:

```sh
python scripts/check_release.py
python scripts/build_release.py --version 1.0.0
```

The build produces three OCI-labeled application images and a local manifest. Docker is
required and was not available in every development environment, so image IDs are produced
only by an actual build, never invented in source. The tag workflow builds, scans, exports,
and checksums the same images. See [deployment and release](docs/runbooks/deployment.md).

## Documentation

- [Architecture and trust boundaries](docs/architecture/overview.md)
- [Event-to-alert sequence](docs/architecture/event-flow.md)
- [REST API endpoints](docs/api/endpoints.md) and [alert workflow](docs/api/alert-workflow.md)
- [Kafka contracts](docs/kafka-events.md) and machine-readable [event schemas](contracts/events)
- [Database model](docs/architecture/data-model.md)
- [Features](docs/ml/feature-definitions.md), [threshold](docs/ml/threshold-strategy.md), and [alert policy](docs/ml/alert-policies.md)
- [Model evaluation and limitations](docs/ml/model-evaluation.md)
- [Deployment](docs/runbooks/deployment.md), [operator investigation](docs/runbooks/operator-investigation.md), [incident response](docs/runbooks/incident-response.md), and [model rollback](docs/runbooks/model-rollback.md)
- [Performance and recovery evidence](docs/performance/results.md)

## Layout

- `apps/api`: FastAPI project, SQLAlchemy repositories, migrations, and API/database tests.
- `apps/worker`: separately packaged Python worker and tests.
- `apps/web`: React, TypeScript, Vite, and the Nginx production proxy.
- `contracts/events`: versioned JSON Schema event contracts and examples.
- `infra`: database initialization, Kafka scripts, and Dockerfile mirrors.
- `observability`: provisioned Grafana dashboards, Prometheus scrapes and tested alert rules.
- `data`: generated synthetic and processed training datasets.
- `model-artifacts`: versioned models, metadata, and evaluation reports.
- `scripts`: local helpers including the HTTP smoke test.
- `docs`: architecture, runbooks, and planning scaffolding.

Compose uses the Dockerfiles in `apps/*`. The copies under `infra/docker` use the
same corresponding app build contexts and should be kept in sync.
No license has been selected yet; `LICENSE` remains a placeholder.
