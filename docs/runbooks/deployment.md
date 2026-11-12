# Deployment and release

Version `1.0.0` can run on one host with Docker Compose, and the API, worker, and web images
can each be built on their own. Compose includes PostgreSQL, Kafka, Redis, Prometheus, and
Grafana for local work and demonstrations. In production, treat those as separately managed
stateful services rather than disposable application containers.

## Required configuration

Copy `.env.example` to a secret-managed environment and replace every development credential. Generate per-user bearer hashes with `scripts/create_auth_user.py`; set `AUTH_USERS` to the resulting JSON array and distribute token files out of band. Configure CORS for the exact web origin. Keep PostgreSQL, Kafka, Redis, worker metrics, Prometheus, and Grafana on private networks. Terminate TLS at the load balancer or ingress; never expose plaintext Kafka or database ports publicly.

Back up PostgreSQL and Kafka according to the recovery runbooks before schema or application changes. Allocate database connections using the documented pool budget. Model, metadata, and threshold files must travel as one reviewed bundle.

## Build immutable images

From a clean `v1.0.0` checkout with Docker BuildKit:

```sh
python scripts/build_release.py --version 1.0.0
```

This builds `transaction-monitoring-api:1.0.0`, `transaction-monitoring-worker:1.0.0`, and `transaction-monitoring-web:1.0.0`, labels them with version/revision/source, and writes image IDs and repository digests to `.local/release/manifest.json`. Docker must be available; the script refuses a version that differs from `VERSION`. The tag-triggered release workflow repeats the build, scans the images, saves them as compressed artifacts, and emits checksums. It does not publish to a registry.

## Rollout order

1. Verify CI, dependency/container scans, model hashes, backups, and the release manifest.
2. Run the one-shot migration image against PostgreSQL and require Alembic head `0009`.
3. Deploy API and verify `/health`, authentication, database access, Redis rate limiting, and Prometheus scrape.
4. Deploy one worker, confirm model version `isolation_forest.v1`, threshold activation, Kafka assignment, and fresh lag.
5. Deploy the web image and verify same-origin `/api` proxy, secure headers, sign-in, dashboard, transaction, and alert pages.
6. Increase worker replicas only within the Kafka partition and database connection budgets.
7. Run smoke, contract, and a controlled end-to-end probe. Do not use the destructive recovery drill on a shared environment.

## Container-engine restart recovery

All long-running Compose services use `restart: unless-stopped`, so PostgreSQL, Redis, Kafka, the API, worker, web application, Prometheus, and Grafana return after a Docker or host restart. The `kafka-init` and `migrate` services deliberately remain one-shot jobs and are not restarted continuously.

After an engine or host restart, verify recovery with:

```sh
docker compose ps
curl --fail http://localhost:8000/health
curl --fail http://localhost:5173/
curl --fail http://localhost:9090/-/healthy
curl --fail http://localhost:3000/api/health
```

Wait for the stateful dependency health checks before judging application recovery, then confirm the worker is consuming and Kafka lag is falling. An explicit `docker compose stop` is remembered by `unless-stopped` and prevents automatic startup by design; resume an intentionally stopped deployment with `docker compose up -d --wait`.

## Rollback

Application images can be rolled back to the prior immutable tag if the schema remains backward-compatible. Do not downgrade database migrations containing production data without a separately reviewed data plan. Follow [model rollback](model-rollback.md) when only scoring regresses. After rollback, verify new ingestion, exact-once receipts, consumer lag, fallback rate, alerts, and operator mutations. Record deployment and rollback times, image IDs, model hash, and migration revision.

## Release tag

Create the annotated tag only on the reviewed release commit:

```sh
git status --short
git tag -a v1.0.0 -m "Production Transaction Monitoring v1.0.0"
git show v1.0.0 --no-patch
```

Pushing code or tags is intentionally a separate, authorized operation.
