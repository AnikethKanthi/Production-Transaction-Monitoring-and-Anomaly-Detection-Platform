# REST API v1.0.0

Interactive OpenAPI is served at `/docs`; the machine contract is `/openapi.json`. Except for `GET /health` and private Prometheus endpoints, send `Authorization: Bearer <token>`. JSON validation failures return 422, missing resources 404, authentication failures 401/403, stale alert versions 409, rate limits 429, and controlled dependency failures 503. Error responses include a safe message and correlation ID; use the response `X-Correlation-ID` when escalating.

| Method | Path | Role | Purpose |
| --- | --- | --- | --- |
| GET | `/health` | Public probe | API liveness and release version |
| GET | `/auth/me` | Operator | Current authenticated username and role |
| POST | `/transactions` | Administrator | Create a transaction directly through the API |
| GET | `/transactions` | Operator | Search, filter, sort, and paginate transactions |
| GET | `/transactions/{transaction_id}` | Operator | Transaction details |
| GET | `/transactions/{transaction_id}/investigation` | Operator | Transaction, anomaly score, and related alerts |
| GET | `/metrics` | Operator | Database/cache dashboard aggregates |
| GET | `/metrics/rolling` | Operator | Redis-backed rolling aggregates |
| GET | `/alerts` | Operator | Filter and paginate the alert queue |
| GET | `/alerts/{alert_id}` | Operator | Evidence, current state, version, and audit history |
| GET | `/alerts/{alert_id}/audit` | Operator | Ordered audit entries only |
| POST | `/alerts/{alert_id}/acknowledge` | Operator | Open → acknowledged |
| POST | `/alerts/{alert_id}/assign` | Operator | Assign or reassign an active alert |
| POST | `/alerts/{alert_id}/resolve` | Operator | Close as resolved |
| POST | `/alerts/{alert_id}/false-positive` | Operator | Close as false positive |
| GET | `/metrics/prometheus` | Private probe | API request/process metrics in Prometheus text format |
| GET | `/metrics/business` | Private probe | Recent database-derived business counters in Prometheus format |

The two Prometheus paths are intentionally omitted from OpenAPI and do not use bearer authentication; expose them only on a private monitoring network. FastAPI also serves `/docs`, `/redoc`, and `/openapi.json` for documentation and contract discovery.

## Transaction query

`GET /transactions` accepts `search`, `status`, `country`, `currency`, `min_amount`, `max_amount`, `start_date`, `end_date`, `sort_by`, `sort_direction`, `limit` (1–100), and `offset`. Search treats SQL wildcard characters literally. Dates are timezone-aware and inclusive. Responses use `{items, pagination: {limit, offset, total}}`.

```http
GET /transactions?status=completed&country=US&currency=USD&sort_by=occurred_at&sort_direction=desc&limit=20&offset=0
Authorization: Bearer <token>
```

## Metrics query

`GET /metrics` requires timezone-aware `start` and exclusive `end`, accepts `interval=hour|day` and optional three-letter `currency`, and returns overall, country, payment-method, and time-series summaries. `GET /metrics/rolling` accepts `window_minutes=1..120`. Anomaly rate means positive model scores and is not the alert rate.

## Alert mutations

All mutations require the displayed positive `expected_version`, a nonblank `reason`, and the compatibility `actor` field; the server overwrites actor with the authenticated username. Assignment also requires `assignee`. Successful changes increment the version and append an audit row in the same transaction.

```json
{
  "expected_version": 2,
  "actor": "ignored-client-value",
  "reason": "Customer confirmed the purchase"
}
```

See [alert workflow](alert-workflow.md) for transition rules and examples. The CI contract check validates these operations and the response fields consumed by the UI against the generated OpenAPI document.
