# Live monitoring dashboard

Run `npm ci --prefix apps/web` and `npm run dev --prefix apps/web`. Open
`http://localhost:5173`. The Vite development server proxies `/api/*` to FastAPI on
`http://127.0.0.1:8000` by default. Set `API_PROXY_TARGET` when the API is elsewhere.
Production Nginx provides the same proxy and falls back to `index.html` for nested routes.

The frontend uses React Router for Overview, Transactions, Alerts, and not-found routes.
TanStack React Query owns fetching, cancellation, caching, and refresh. Dashboard metrics
and service health refresh every 30 seconds while the tab is active. Queries are fresh for
15 seconds and automatic error retries are disabled; users can retry explicitly. Requests
time out after eight seconds. HTTP errors include correlation IDs when the API provides them.

The dashboard calls `GET /metrics` with timezone-aware start/end, hour/day interval, and
one selected currency. Supported windows are 24 hours, seven days, and 30 days. Amounts
never combine currencies. Timestamps and chart buckets use UTC. The API's database/cache
source and reporting cutoff are visible so old data is not mistaken for the current moment.

KPIs show transaction count, total and average amount, success rate, and anomaly rate.
Volume charts zero-fill missing time buckets. Anomaly charts preserve gaps for periods
without transactions rather than inventing a zero rate. Status distribution uses success,
decline, refund rates and the remaining share as pending (subject to API rounding).
Anomaly rate is the backend's positive-model-score definition, not alert volume.

Initial loads show skeletons, empty datasets show an explicit empty state, and failures show
an error with a retry button. If a refresh fails after a successful load, the previous result
remains visible and is explicitly marked as last-successful data. No production mock data
or silent fixture fallback is included. A healthy API does not guarantee database availability;
the health indicator and metric request errors are shown independently.

Transactions includes a paginated ledger. Alerts includes the latest 50 matching alerts and
a status filter. These are read-only navigation views; investigation actions remain available
through the existing API. Dashboard chart data is also available as a text table. Navigation,
filters, and controls support keyboard focus. Layouts adapt at desktop and tablet widths,
and motion effects respect reduced-motion preferences.

Validate with `npm run build --prefix apps/web` and `npm run test:e2e --prefix apps/web`.
Install the browser first if necessary: `cd apps/web && npx playwright install chromium`.
Browser tests use intercepted HTTP fixtures matching the metrics contract, exercise error
recovery and navigation, and capture screenshots at 1440, 1024, and 768 pixels. To verify
deployment end to end, start the real FastAPI/PostgreSQL/Redis services and ensure there
are transactions in the selected currency and reporting period.
