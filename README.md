# Production Transaction Monitoring

Day 1 bootstrap for a transaction monitoring monorepo: FastAPI, a standalone Python
worker, React with TypeScript, PostgreSQL, Redis, and Apache Kafka in KRaft mode.
Transaction ingestion, database models, anomaly detection, and alerts are future work.

## Start locally with Docker

Install Docker Desktop with Linux containers and Docker Compose. Allow about 4 GB
of memory for the local stack. From the repository root:

```sh
docker compose config --quiet
docker compose up --build -d --wait --wait-timeout 240
python scripts/smoke_test.py
```

The defaults work without an `.env` file. To customize ports or credentials, copy
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

`GET /health` returns `{"status":"ok","service":"api","version":"0.1.0"}`.
It checks API liveness. Compose independently checks PostgreSQL, Redis, Kafka, API,
and web health; the worker runs in bootstrap mode and logs periodic heartbeats.
The frontend checks the real API through a same-origin `/api` proxy.

```sh
docker compose ps
docker compose logs --tail=100
docker compose down
```

Named volumes preserve infrastructure data when containers stop. On later runs,
the existing PostgreSQL volume retains its original credentials. If a host port is
occupied, change its value in `.env`; pass the changed API/web URLs to the smoke script.

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

The development UI proxies requests to `http://127.0.0.1:8000`. Set
`API_PROXY_TARGET` if the API runs at a different address. The Day 1 applications
do not access the infrastructure yet, so they can also run without those services.

## Validate

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
and container smoke tests on pushes and pull requests. Dependency auditing runs
on pull requests or manual dispatch. These workflows run when changes reach GitHub.

## Layout

- `apps/api`: FastAPI project, API tests, and migration scaffolding.
- `apps/worker`: separately packaged Python worker and tests.
- `apps/web`: React, TypeScript, Vite, and the Nginx production proxy.
- `contracts/events`: reserved event contracts and examples.
- `infra`: database initialization, Kafka scripts, and Dockerfile mirrors.
- `observability`: reserved Prometheus and Grafana configuration.
- `data` and `model-artifacts`: directories for later ML work.
- `scripts`: local helpers including the HTTP smoke test.
- `docs`: architecture, runbooks, and planning scaffolding.

Compose uses the Dockerfiles in `apps/*`. The copies under `infra/docker` use the
same corresponding app build contexts and should be kept in sync.
Files outside the Day 1 implementation remain placeholders. No license has been
selected yet; `LICENSE` remains a placeholder.
