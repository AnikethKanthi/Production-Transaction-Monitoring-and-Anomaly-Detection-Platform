# Local development

Follow the README quick start for the supported Docker path. For application development, use Python 3.12+, Node 22.12+, PostgreSQL 17, Redis 7.4, and Kafka 4.1.2. Direct dependencies are pinned in both Python projects and `package.json`; `package-lock.json` fixes the complete frontend graph.

Create and activate `.venv`, then install `-e "apps/api[dev,ml]" -e "apps/worker[dev]"`. Run Uvicorn with `PYTHONPATH=apps/api`, the worker with `PYTHONPATH=apps/worker`, and `npm run dev` from `apps/web`. Infrastructure can remain in Compose. Never reuse production credentials or databases; integration tests require an explicit disposable `TEST_DATABASE_URL` and isolate schemas.

Before handing off a change, run Ruff check/format, API and worker tests separately, `npm ci`, the frontend build, Playwright, `scripts/check_release.py`, Compose configuration validation, smoke checks, and contract checks. The complete commands and CI boundaries are in [testing](../testing.md).
