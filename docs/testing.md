# End-to-end testing and CI

The CI pipeline validates the application at three levels:

- API and worker unit/integration tests, migration tests, frontend build, and mocked browser tests.
- A clean Compose test that sends real Kafka events through the worker, PostgreSQL, API, and React UI.
- Python and npm dependency audits plus high/critical vulnerability scans of the API, worker, and web images.

## Live workflow

The `end-to-end` CI job creates a disposable operator token and a fresh Compose project. It publishes twelve deterministic history events and one outlier to `transactions.v1`. The test then requires:

1. Kafka delivery and worker processing.
2. Transaction, feature, anomaly, alert, and audit persistence.
3. Scoring by `isolation_forest.v1` rather than fallback behavior.
4. Transaction, investigation, alert, metrics, and OpenAPI responses through the deployed API.
5. A non-zero anomaly rate in the live dashboard.
6. Visible model evidence on the transaction and alert pages.
7. Alert resolution through the browser and a persisted `resolve` audit entry.

The fixture is also scored in the worker unit suite. If model training or threshold tuning makes it cease to qualify, CI fails before the live test can silently stop covering alert creation.

## Run locally

Docker and a Chromium-compatible Playwright browser are required. Never point these commands at a shared or production stack.

```powershell
.venv\Scripts\python.exe scripts\create_auth_user.py --username e2e-operator --role operator --token-file .local\e2e.token > .local\e2e-user.json
# Set AUTH_USERS to a JSON array containing .local/e2e-user.json, then:
docker compose -p e2e-local up --build -d --wait api worker web
.venv\Scripts\python.exe scripts\smoke_test.py
.venv\Scripts\python.exe scripts\check_contracts.py
.venv\Scripts\python.exe scripts\run_end_to_end.py prepare --token-file .local\e2e.token
```

Run the single live browser scenario from `apps/web` with `E2E_CONTEXT_FILE` set to the absolute `.local/e2e-context.json` path, `PLAYWRIGHT_EXTERNAL_SERVER=1`, and `PLAYWRIGHT_BASE_URL=http://127.0.0.1:5173`. Then run:

```powershell
.venv\Scripts\python.exe scripts\run_end_to_end.py verify
docker compose -p e2e-local down -v
```

The context file contains record identifiers and an absolute path to the private token file; both remain under ignored `.local/`. CI artifacts exclude them. Failure artifacts contain service logs and browser traces only, and the logging redaction tests protect payment fields and authorization values.

## Contract and smoke boundaries

`scripts/check_contracts.py` validates the deployed OpenAPI operations and response fields consumed by the operator workflow. API behavior is covered separately by repository and route tests; the browser test catches drift between those schemas and the TypeScript client.

`scripts/smoke_test.py` checks direct API health, the web-to-API proxy, the React entry document, and proxied OpenAPI availability. The live workflow is intentionally separate because it mutates disposable data and resolves an alert.

The Python audit runs in a fresh isolated environment with eagerly upgraded transitive dependencies, so packages left in a developer or runner environment cannot affect the result. Dependency and image scans fail CI for known high or critical vulnerabilities with available fixes. Scan databases evolve over time, so a failure must be triaged: upgrade the affected direct or transitive dependency, rebuild, and document any time-bounded exception rather than disabling the scanner.
