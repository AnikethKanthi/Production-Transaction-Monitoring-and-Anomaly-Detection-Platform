# Alert investigation API

Apply migration `0007` before running the API or worker. New alerts start `open`, unassigned,
at version 1. The worker writes a `create` audit entry in the alert transaction. Migration
backfills existing alerts with an `import` audit entry and explicitly records that prior
workflow history is unavailable. Downgrading removes workflow fields and audit history.

| Method | Endpoint | Behavior |
| --- | --- | --- |
| GET | `/alerts?status=open&severity=high&limit=50&offset=0` | Filtered list with pagination and total |
| GET | `/alerts/{id}` | Alert, model evidence, current version, and ordered audit history |
| GET | `/alerts/{id}/audit` | Audit entries ordered by version |
| POST | `/alerts/{id}/acknowledge` | Open to acknowledged |
| POST | `/alerts/{id}/assign` | Assign or reassign an open/acknowledged alert |
| POST | `/alerts/{id}/resolve` | Open/acknowledged to resolved |
| POST | `/alerts/{id}/false-positive` | Open/acknowledged to false_positive |

Both status and severity filters can be combined. Lists sort newest first with ID as a
stable tie-breaker. Limit is 1–100; offset is nonnegative. Closed alerts are immutable through
these endpoints. Repeated acknowledgements and assignment to the same assignee are rejected.
Assignment leaves the investigation status unchanged. No endpoint edits evidence or severity.

Every mutation requires a JSON body:

```json
{
  "expected_version": 1,
  "actor": "analyst-17",
  "reason": "Investigating unusual transaction activity"
}
```

Assignment additionally requires `"assignee": "analyst-23"`. Version must be a positive
integer; actor, reason, and assignee must be nonblank. Unknown fields are rejected. Successful
mutations return the updated alert and increment its version by one. Use that returned version
on the next request. Actor is a caller-supplied audit identifier, not authenticated identity;
this repository has no analyst authentication or authorization system yet.

Optimistic concurrency is enforced by an atomic SQL update matching ID and expected version,
not only a read-before-write check. A competing or stale update returns HTTP 409 with code
`alert_version_conflict`; reload details before retrying. Invalid state changes return HTTP
409 with `invalid_alert_transition`. Missing alerts return 404 and invalid inputs return 422.

Audit rows include action, actor, reason, old/new status and assignee, version, and database
timestamp. State update, version increment, and audit insertion share one transaction. Failed
mutations append no audit row; audit insertion failure rolls back the mutation. Unique
`(alert_id, version)` prevents multiple audit entries for one workflow version. API routes
provide read access only to history. Audit history follows alert retention: deleting an alert
directly in the database cascades its audit rows.
