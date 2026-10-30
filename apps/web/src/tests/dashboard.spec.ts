import { expect, test, type Page } from '@playwright/test';

function fixture(url: string, empty = false) {
  const params = new URL(url).searchParams;
  const end = params.get('end')!;
  const summary = {
    label: 'all',
    transaction_count: empty ? 0 : 1200,
    transaction_amount: empty ? 0 : 149000,
    average_transaction_amount: empty ? 0 : 124.1667,
    success_rate: empty ? 0 : 0.9,
    decline_rate: empty ? 0 : 0.06,
    refund_rate: empty ? 0 : 0.02,
    anomaly_rate: empty ? 0 : 0.025,
    average_processing_latency_ms: 12.5,
  };
  const step = params.get('interval') === 'hour' ? 3_600_000 : 86_400_000;
  return {
    start: params.get('start'),
    end,
    interval: params.get('interval'),
    currency: params.get('currency'),
    source: 'database',
    overall: summary,
    by_country: empty ? [] : [{ ...summary, label: 'US' }],
    by_payment_method: empty ? [] : [{ ...summary, label: 'card' }],
    time_series: empty
      ? []
      : Array.from({ length: 4 }, (_, index) => ({
          ...summary,
          transaction_count: 300,
          label: new Date(
            Math.floor(Date.parse(end) / step) * step - (4 - index) * step,
          ).toISOString(),
        })),
  };
}

async function mockMetrics(page: Page) {
  await page.route('**/api/metrics?*', (route) =>
    route.fulfill({ json: fixture(route.request().url()) }),
  );
}

test.beforeEach(async ({ page }) => {
  await page.route('**/api/health', (route) =>
    route.fulfill({ json: { status: 'ok', service: 'api', version: '0.1.0' } }),
  );
});

test('loads API KPIs and all three charts without browser errors', async ({
  page,
}) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await mockMetrics(page);
  await page.goto('/');
  await expect(
    page.getByRole('heading', { name: 'Transaction overview' }),
  ).toBeVisible();
  await expect(page.getByText('1,200', { exact: true })).toBeVisible();
  await expect(
    page.getByText('$149,000.00', { exact: true }).first(),
  ).toBeVisible();
  await expect(
    page.getByRole('img', { name: /Transaction volume chart/ }),
  ).toBeVisible();
  await expect(
    page.getByRole('img', { name: /Status distribution:/ }),
  ).toBeVisible();
  await expect(
    page.getByRole('img', { name: /Anomaly rate chart/ }),
  ).toBeVisible();
  await expect(page.getByText('API online · v0.1.0')).toBeVisible();
  await page.getByText('View chart data as a table').click();
  await expect(
    page.getByRole('columnheader', { name: 'Bucket (UTC)' }),
  ).toBeVisible();
  expect(errors).toEqual([]);
});

test('changes range and currency in live API requests', async ({ page }) => {
  await mockMetrics(page);
  await page.goto('/');
  await expect(page.getByText('1,200', { exact: true })).toBeVisible();
  const request = page.waitForRequest(
    (request) =>
      request.url().includes('/api/metrics?') &&
      new URL(request.url()).searchParams.get('interval') === 'day',
  );
  await page.getByRole('button', { name: '7 days', exact: true }).click();
  await request;
  await expect(
    page.getByRole('button', { name: '7 days', exact: true }),
  ).toHaveAttribute('aria-pressed', 'true');
  await page.getByLabel('Currency').selectOption('GBP');
  await expect(
    page.getByText('£149,000.00', { exact: true }).first(),
  ).toBeVisible();
});

test('shows loading and honest empty state', async ({ page }) => {
  await page.route('**/api/metrics?*', async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 450));
    await route.fulfill({ json: fixture(route.request().url(), true) });
  });
  await page.goto('/');
  await expect(
    page.getByRole('status', { name: 'Loading live data' }),
  ).toBeVisible();
  await expect(
    page.getByRole('heading', { name: 'No transactions in this period' }),
  ).toBeVisible();
  await expect(
    page.getByRole('img', { name: /Transaction volume chart/ }),
  ).toHaveCount(0);
});

test('displays API failure and recovers on retry', async ({ page }) => {
  await page.route('**/api/metrics?*', (route) =>
    route.fulfill({
      status: 503,
      headers: { 'x-correlation-id': 'trace-17' },
      json: { error: 'unavailable' },
    }),
  );
  await page.goto('/');
  await expect(page.getByRole('alert')).toContainText('HTTP 503');
  await expect(page.getByRole('alert')).toContainText('trace-17');
  await page.unroute('**/api/metrics?*');
  await mockMetrics(page);
  await page.getByRole('button', { name: 'Try again' }).click();
  await expect(page.getByText('1,200', { exact: true })).toBeVisible();
});

test('rejects malformed metrics instead of displaying invented data', async ({
  page,
}) => {
  await page.route('**/api/metrics?*', (route) =>
    route.fulfill({ json: { overall: null } }),
  );
  await page.goto('/');
  await expect(page.getByRole('alert')).toContainText(
    'unexpected metrics response',
  );
});

test('keeps last good data visible with a clear refresh error', async ({
  page,
}) => {
  await mockMetrics(page);
  await page.goto('/');
  await expect(page.getByText('1,200', { exact: true })).toBeVisible();
  await page.unroute('**/api/metrics?*');
  await page.route('**/api/metrics?*', (route) => route.abort());
  await page.getByRole('button', { name: 'Refresh data' }).click();
  await expect(page.getByRole('alert')).toBeVisible();
  await expect(page.getByText('1,200', { exact: true })).toBeVisible();
  await expect(page.getByText(/Last successful data/)).toBeVisible();
});

test('navigates and supports direct nested routes', async ({ page }) => {
  await mockMetrics(page);
  await page.route('**/api/transactions?*', (route) =>
    route.fulfill({ json: { items: [], pagination: { total: 0 } } }),
  );
  await page.route('**/api/alerts?*', (route) =>
    route.fulfill({ json: { items: [], pagination: { total: 0 } } }),
  );
  await page.goto('/');
  await page.getByRole('link', { name: 'Transactions', exact: false }).click();
  await expect(
    page.getByRole('heading', { name: 'Transactions', exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(page.getByText('No transactions found')).toBeVisible();
  await page.getByRole('link', { name: 'Alerts', exact: false }).click();
  await expect(page.getByText('No alerts found')).toBeVisible();
  await page.goto('/not-a-real-route');
  await expect(page.getByText('Page not found')).toBeVisible();
});

for (const width of [1440, 1024, 768]) {
  test(`dashboard fits ${width}px with accessible navigation`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 1100 });
    await mockMetrics(page);
    await page.goto('/');
    await expect(
      page.getByRole('img', { name: /Anomaly rate chart/ }),
    ).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
    await expect(
      page.getByRole('navigation', { name: 'Main navigation' }),
    ).toBeVisible();
    await page.screenshot({
      path: `test-results/dashboard-${width}.png`,
      fullPage: true,
    });
  });
}
