# Security and resilience

## Provision users

Every business API request needs a bearer token issued to a specific user. The project has
no default login and no authentication bypass: with `AUTH_USERS=[]`, every protected request
is rejected. Create local credentials from the repository root:

```sh
python scripts/create_auth_user.py --username analyst-17 --role operator --token-file .local/analyst-17.token
python scripts/create_auth_user.py --username admin-1 --role administrator --token-file .local/admin-1.token
```

The helper saves a random 256-bit token exclusively to the requested file and prints
only a server configuration entry containing its SHA-256 hash. Existing files cannot
be overwritten. `.local/` and `*.token` are ignored by Git. POSIX creation mode is 0600;
on Windows restrict the containing directory with NTFS permissions or use your secret
manager. Never put tokens in shell arguments, logs, URLs, source, issues or screenshots.

Combine the printed entries into a JSON array in `.env`:

```dotenv
AUTH_USERS='[{"username":"analyst-17","role":"operator","token_sha256":"<64-character-sha256>"},{"username":"admin-1","role":"administrator","token_sha256":"<different-64-character-sha256>"}]'
```

Recreate the API container/restart Uvicorn after changes. Hash comparisons use constant
time; duplicate usernames/hashes and unknown roles are rejected. Rotation/revocation
means replacing/removing the hash and restarting every API instance. These static
tokens have no automatic expiry, MFA, refresh or recovery flow. Use TLS remotely and
a managed identity provider when those capabilities are needed.

The frontend sign-in screen calls `/auth/me`. Credentials stay only in JavaScript
memory; refresh signs out. Sign-out/401 clear credentials and React Query caches.
API clients send `Authorization: Bearer <token>`; Swagger supports Authorize.

| Capability | Operator | Administrator |
| --- | --- | --- |
| Read transactions, investigations, alerts, audits and dashboard APIs | Yes | Yes |
| Acknowledge, assign, resolve, mark false positive | Yes | Yes |
| Create transactions through HTTP | No (403) | Yes |

The server replaces the validated compatibility `actor` field with the authenticated
username before recording alert audit history. The UI shows this identity read-only.
Assignee is a workflow label, not an identity grant. Roles do not isolate tenants.
`/health`, `/metrics/prometheus`, `/metrics/business`, schema and docs remain public for
probes; aggregate monitoring data must stay on a private monitoring network. Compose
host bindings remain loopback. Worker Kafka ingestion is outside HTTP authentication;
the supplied local broker network is plaintext.

## HTTP protections

`CORS_ORIGINS` requires explicit JSON origins (defaults: local Vite origins), with no
cookie credentials or wildcard. Authorization/content-type/correlation headers are
allowed. CORS is a browser policy; bearer authorization also protects non-browser calls.

API request protection adds no-store, nosniff, frame denial, no-referrer and restrictive
permissions headers. JSON endpoints have deny-all CSP; Swagger/ReDoc are exempt for
their scripts. HTTPS adds HSTS. Nginx protects React assets with CSP (same-origin
scripts/connections, no frames), disables access logs and enforces 64 KiB bodies.
Configure TLS and HSTS at the public TLS terminator for remote deployment.

API bodies default to 65,536 bytes, counted even for chunked uploads (413), with a
five-second absolute upload deadline (408). Duplicate/invalid content-length returns
400; compressed bodies return 415. Nginx separately enforces a five-second idle timeout.
API limits are configurable in `.env`; the independent Nginx ceiling remains 64 KiB.

Redis shares atomic fixed-window limits across API instances using a Lua INCR+EXPIRE
operation: default 120 requests/user/60s and five times that budget per source IP,
including invalid-token attempts. Keys contain hashes and expire. 429 includes
Retry-After. Preflight/probes bypass limits; Redis failures fail closed with 503.
Application code uses the ASGI client IP, not raw forwarded headers. Nginx users may
share its IP budget: configure proxy trust only for an explicitly trusted network.
Requests rejected before authentication do not consume the per-user budget.

## Dependency bounds and recovery

| Dependency | Behavior |
| --- | --- |
| PostgreSQL | Connect/pool acquisition 3s, statement 5s, lock wait 2s. SQL parameters hidden. Per-operation bounds, not a total request deadline. |
| Redis | Connect/socket 1s each, client retries disabled. Security enforcement fails closed, cache reads fall back to PostgreSQL, rolling-only API returns 503, worker counters are best effort. |
| Kafka | Socket 5s, producer delivery/flush 10s, reconnect backoff 250ms–10s, producer backoff 250ms–2s. Transient poll faults wait with jitter; fatal errors exit. |
| Worker processing | Default 3 attempts with capped exponential full jitter. Transient database/pool failures exit uncommitted for replay; permanent/other exhausted failures publish DLQ before commit. Failed DLQ/commit never counts success. Compose supervises restart. |
| Model | Missing/incompatible model, exceptions or non-finite output store score 0, `fallback.v1`, safe failure category and fallback metrics. Local synchronous inference has no hard timeout for a hung native call. |
| HTTP | Frontend 8s; Nginx upstream connect 3s, send 5s, read 15s. Writes are not automatically retried: timeout does not prove rollback. |

Database/Redis exceptions return sanitized 503; integrity conflicts return 409. Responses
omit SQL, parameters, connection URLs and raw dependency exceptions. Validation omits
submitted values; transaction input rejects unknown/card fields. Represent payments by
references, never PAN/CVV. Load joblib artifacts only from trusted sources.

## Sensitive data in logs

API/worker JSON logs retain route templates, IDs, status, duration and exception class.
Bodies, authorization headers, raw Kafka payloads, SQL parameters and exception text/
tracebacks are not logged. Model failure records and DLQ error metadata omit raw exception
messages. Original DLQ payloads remain encoded data for replay: restrict their access
and retention separately.

Both formatters also redact common PAN forms (13–19 digits), CVV/CVC, bearer strings,
password/token/key assignments, URL userinfo and environment secret literals. UUIDs
remain traceable. HTTP-client, SQL-engine and Uvicorn access logs are suppressed to
avoid raw URLs/query strings. This is defense in depth: never submit credentials or
card data in free-text fields/correlation IDs or enable raw third-party logging.

## Verification

API tests exercise real authentication with a fake limiter and verify roles, audit
spoof prevention, sanitized PostgreSQL/Redis errors, fail-closed limits, CORS/headers,
streamed limits and upload deadlines. Domain tests explicitly override identity without
changing production auth. Worker tests inject PostgreSQL/Redis/Kafka/model failures,
check jitter, DLQ/commit ordering, recovery, fallback and log redaction. Browser tests
cover sign-in/out, memory-only tokens, refresh, 401 cache clearing and existing workflows.

```sh
python -m pytest apps/api/tests
python -m pytest apps/worker/tests
npm run build --prefix apps/web
npm run test:e2e --prefix apps/web
```

Set `TEST_DATABASE_URL` for isolated PostgreSQL schema tests and `TEST_REDIS_URL` for
concurrent atomic limiter/expiration testing. CI supplies both services. Real-service
tests skip without these URLs. Kafka outage tests use controllable client doubles.
Docker is required to validate Nginx/Compose against live dependencies.
