# Operator investigation workflow

Sign in with an issued token before investigating records. Refreshing signs out while
preserving the URL filters. See [security and resilience](security-resilience.md).

## Transactions

Open `/transactions`. Search matches account/merchant text case-insensitively and a full
transaction UUID exactly. SQL wildcard characters in account/merchant searches are literal.
Filters combine status, country, currency, amount bounds, and inclusive UTC dates. Use
**Apply filters** or submit the form with Enter. Clear filters restores the default list.

Amount, country, status, and time column buttons sort ascending/descending; transaction ID
breaks ties deterministically in the same direction. Amount sorting uses nominal amounts,
not currency conversion, so select a currency for meaningful monetary comparisons.
Pagination and page size are server-side. Changing filters, sort, or size resets the offset.
Search, filters, sorting, size, and offset live in URL parameters, survive reload and browser
back/forward navigation, and are retained by the back link from transaction details.

Select a transaction ID to open `/transactions/{id}`. The screen calls the new
`GET /transactions/{id}/investigation` endpoint, displaying transaction context, the stored
score/model/status, and related alerts. Unscored transactions are explicitly marked as such;
fallback scores are not presented as a reliable risk assessment. Follow an alert link to
investigate its evidence or open the queue with a `transaction_id` filter.

## Alerts

Open `/alerts` and filter by status, severity, or transaction UUID. Filters and pagination
are URL-backed. Select an alert ID to open details, inspect the score, threshold, reasons,
and observed features, and read version-ordered audit history. Observed features are context,
not a causal explanation of the model. The queue supports paging beyond its first 20 results.

Choose an action, review your authenticated operator ID, enter an investigation note,
and apply the action:

1. Acknowledge an open alert.
2. Assign or reassign an open/acknowledged alert to an operator or team identifier.
3. Resolve the investigation or mark it as a false positive.

Every mutation sends the displayed `expected_version`. Buttons are disabled while saving
or refreshing details. Successful actions reload detail/audit data, invalidate related list
and transaction queries, and announce completion. Terminal alerts show a read-only state.
The operator identifier is read-only; the API derives audit actors from authentication.

HTTP 409 displays a conflict and offers **Reload latest alert**. The client never silently
replays failed mutations. Read the latest version before resubmitting. Network failure may
occur after a server commit, so reload before retrying even when no success was shown.

## Keyboard and accessibility

Navigation and IDs are native links. Search/filter forms submit with Enter; sorting and
pagination use native buttons. All inputs have labels and required fields use browser
validation. Tables provide scoped headings and captions; sortable headings expose
`aria-sort`. The main region receives focus on path changes and the success announcement
receives focus after a mutation. Error and completion states use live-region roles.
There are no click-only rows or custom focus traps. Long identifiers wrap in details;
wide tables scroll inside their own container at tablet widths.

## Validation

Run `npm run build --prefix apps/web` and browser tests with
`npm run test:e2e --prefix apps/web` (or set `PLAYWRIGHT_CHANNEL=chrome` to use installed
Chrome). The browser suite checks URL persistence, keyboard entry into investigations,
full acknowledge/assign/resolve flow, false-positive closure, stale-version conflict,
required fields, errors, and tablet layout using API-contract fixtures.
Database-backed API tests exercise actual SQL search, safe sorting, UUID lookup, and
score/alert joins on isolated SQLite fixtures. Existing PostgreSQL integration tests
require `TEST_DATABASE_URL`. No new schema migration is required for this task.
