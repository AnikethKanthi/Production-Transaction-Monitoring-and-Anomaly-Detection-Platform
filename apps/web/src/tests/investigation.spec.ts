import { signIn, visitAuthenticated } from './auth-helper';
import { expect, test, type Page } from '@playwright/test';
import type { AuditEntry } from '../api/investigations';

const transactionId = '11111111-1111-4111-8111-111111111111';
const alertId = '22222222-2222-4222-8222-222222222222';
const transaction = {
  id: transactionId,
  account_id: 'acct-17',
  merchant_id: 'shop-1',
  amount: '5000.00',
  currency: 'USD',
  country: 'US',
  status: 'completed',
  occurred_at: '2026-11-02T12:00:00Z',
  payment_method: 'card',
  device_id: 'new-device',
  ip_address: '198.51.100.5',
  order_amount: '5000',
};

async function setup(page: Page, conflict = false) {
  const audit: AuditEntry[] = [
    {
      id: 'audit-1',
      version: 1,
      action: 'create',
      actor: 'system:worker',
      reason: 'Score exceeded threshold',
      before: null,
      after: { status: 'open', assignee: null as string | null },
      created_at: '2026-11-02T12:00:00Z',
    },
  ];
  let alert = {
    id: alertId,
    transaction_id: transactionId,
    severity: 'high',
    status: 'open',
    assignee: null as string | null,
    version: 1,
    model_version: 'isolation_forest.v1',
    policy_version: 'anomaly_alert.v1',
    evidence: {
      score: 0.4,
      threshold: 0.229602,
      reasons: ['Score exceeded the configured alert threshold.'],
      observed_features: { transaction_amount: 5000, new_device_indicator: 1 },
    },
    created_at: '2026-11-02T12:00:00Z',
  };
  const mutations: Record<string, unknown>[] = [];
  await page.route('**/api/health', (route) =>
    route.fulfill({ json: { status: 'ok', service: 'api', version: '1.0.0' } }),
  );
  await page.route('**/api/transactions?*', (route) =>
    route.fulfill({
      json: {
        items: [transaction],
        pagination: {
          limit: 20,
          offset: Number(
            new URL(route.request().url()).searchParams.get('offset') || 0,
          ),
          total: 41,
        },
      },
    }),
  );
  await page.route(
    `**/api/transactions/${transactionId}/investigation`,
    (route) =>
      route.fulfill({
        json: {
          transaction,
          anomaly: {
            score: 0.4,
            model_version: 'isolation_forest.v1',
            scoring_status: 'scored',
            inference_latency_seconds: 0.02,
            failure_reason: null,
          },
          alerts: [alert],
        },
      }),
  );
  await page.route('**/api/alerts?*', (route) =>
    route.fulfill({
      json: { items: [alert], pagination: { limit: 20, offset: 0, total: 1 } },
    }),
  );
  await page.route(`**/api/alerts/${alertId}**`, async (route) => {
    if (route.request().method() === 'GET')
      return route.fulfill({ json: { ...alert, audit_history: audit } });
    const body = route.request().postDataJSON() as Record<string, unknown>;
    mutations.push(body);
    if (conflict) {
      conflict = false;
      alert = { ...alert, version: 2, assignee: 'other-operator' };
      return route.fulfill({
        status: 409,
        json: { error: { message: 'Alert version conflict' } },
      });
    }
    if (body.expected_version !== alert.version)
      return route.fulfill({
        status: 409,
        json: { error: { message: 'Alert changed' } },
      });
    const action = new URL(route.request().url()).pathname.split('/').pop()!;
    const before = { status: alert.status, assignee: alert.assignee };
    alert = {
      ...alert,
      version: alert.version + 1,
      status:
        action === 'acknowledge'
          ? 'acknowledged'
          : action === 'resolve'
            ? 'resolved'
            : action === 'false-positive'
              ? 'false_positive'
              : alert.status,
      assignee: action === 'assign' ? String(body.assignee) : alert.assignee,
    };
    audit.push({
      id: `audit-${alert.version}`,
      version: alert.version,
      action,
      actor: String(body.actor),
      reason: String(body.reason),
      before,
      after: { status: alert.status, assignee: alert.assignee },
      created_at: '2026-11-02T12:01:00Z',
    });
    return route.fulfill({ json: alert });
  });
  return mutations;
}

test('finds transactions using URL filters, sort, pagination and keyboard investigation', async ({
  page,
}) => {
  await setup(page);
  await visitAuthenticated(page, '/transactions?status=completed&country=US');
  await expect(
    page.getByRole('combobox', { name: 'Status', exact: true }),
  ).toHaveValue('completed');
  await page.getByLabel('Search transactions').fill('acct-17');
  await page.getByRole('button', { name: 'Apply filters' }).click();
  await expect(page).toHaveURL(/search=acct-17/);
  await expect(page).toHaveURL(/country=US/);
  await page.getByRole('button', { name: /^Amount/ }).click();
  await expect(page).toHaveURL(/sort_by=amount/);
  await expect(
    page.getByRole('columnheader', { name: /Amount/ }),
  ).toHaveAttribute('aria-sort', 'descending');
  await page.getByRole('button', { name: 'Next', exact: true }).click();
  await expect(page).toHaveURL(/offset=20/);
  await page.reload();
  await signIn(page);
  await expect(page.getByLabel('Search transactions')).toHaveValue('acct-17');
  const link = page.getByRole('link', {
    name: `Investigate transaction ${transactionId}`,
  });
  await link.focus();
  await page.keyboard.press('Enter');
  await expect(
    page.getByRole('heading', { name: 'Transaction investigation' }),
  ).toBeVisible();
  await expect(page.getByText('0.400000', { exact: true })).toBeVisible();
  await expect(
    page.getByRole('link', { name: 'Investigate alert 22222222' }),
  ).toBeVisible();
  await page
    .getByRole('link', { name: 'Back to filtered transactions', exact: false })
    .click();
  await expect(page).toHaveURL(/offset=20/);
  await expect(page.getByLabel('Search transactions')).toHaveValue('acct-17');
  await page.getByRole('button', { name: 'Clear filters' }).click();
  await expect(
    page.getByRole('combobox', { name: 'Status', exact: true }),
  ).toHaveValue('');
});

test('filters queue and completes acknowledge assign resolve lifecycle with audit', async ({
  page,
}) => {
  const mutations = await setup(page);
  await visitAuthenticated(page, '/alerts?severity=high&status=open');
  await expect(page.getByLabel('Severity')).toHaveValue('high');
  await page
    .getByRole('link', { name: `Investigate alert ${alertId}` })
    .click();
  await expect(
    page.getByRole('heading', { name: 'Alert investigation' }),
  ).toBeVisible();
  await expect(page.getByText('0.400000', { exact: true })).toBeVisible();
  await page.getByText('Observed inference features', { exact: true }).click();
  await expect(
    page.getByText('new device indicator', { exact: true }),
  ).toBeVisible();
  await page
    .getByRole('combobox', { name: 'Action', exact: true })
    .selectOption('acknowledge');
  await expect(page.getByLabel('Your operator ID')).toHaveValue('operator-17');
  await page
    .getByLabel('Investigation note')
    .fill('Reviewing new device evidence');
  await page.getByRole('button', { name: 'Apply action' }).click();
  await expect(page.getByText('Version 2', { exact: true })).toBeVisible();
  await page
    .getByRole('combobox', { name: 'Action', exact: true })
    .selectOption('assign');
  await page.getByLabel('Assign to', { exact: true }).fill('fraud-team-1');
  await page
    .getByLabel('Investigation note')
    .fill('Assigned for specialist review');
  await page.getByRole('button', { name: 'Apply action' }).click();
  await expect(page.getByText('Version 3', { exact: true })).toBeVisible();
  await page
    .getByRole('combobox', { name: 'Action', exact: true })
    .selectOption('resolve');
  await page.getByLabel('Investigation note').fill('Investigation completed');
  await page.getByRole('button', { name: 'Apply action' }).click();
  await expect(page.getByText(/This alert is closed/)).toBeVisible();
  await expect(
    page.getByText('Version 4 · resolve', { exact: true }),
  ).toBeVisible();
  expect(mutations.map((body) => body.expected_version)).toEqual([1, 2, 3]);
  expect(mutations.every((body) => body.actor === 'operator-17')).toBe(true);
  await page
    .getByRole('link', { name: 'Back to filtered alerts', exact: false })
    .click();
  await expect(page).toHaveURL(/severity=high&status=open/);
});

test('shows a conflict without retrying and reloads latest version', async ({
  page,
}) => {
  const mutations = await setup(page, true);
  await visitAuthenticated(page, `/alerts/${alertId}`);
  await page
    .getByRole('combobox', { name: 'Action', exact: true })
    .selectOption('resolve');
  await expect(page.getByLabel('Your operator ID')).toHaveValue('operator-17');
  await page.getByLabel('Investigation note').fill('Resolved after review');
  await page.getByRole('button', { name: 'Apply action' }).click();
  await expect(page.getByRole('alert')).toContainText('This alert changed');
  expect(mutations).toHaveLength(1);
  await page.getByRole('button', { name: 'Reload latest alert' }).click();
  await expect(page.getByText('Version 2', { exact: true })).toBeVisible();
  await expect(page.getByText('other-operator', { exact: true })).toBeVisible();
  expect(mutations).toHaveLength(1);
});

test('false positive closure is available and empty required fields prevent submission', async ({
  page,
}) => {
  const mutations = await setup(page);
  await visitAuthenticated(page, `/alerts/${alertId}`);
  await page
    .getByRole('combobox', { name: 'Action', exact: true })
    .selectOption('false-positive');
  await page.getByRole('button', { name: 'Apply action' }).click();
  expect(mutations).toHaveLength(0);
  await expect(page.getByLabel('Your operator ID')).toHaveValue('operator-17');
  await page
    .getByLabel('Investigation note')
    .fill('Legitimate customer purchase');
  await page.getByRole('button', { name: 'Apply action' }).click();
  await expect(page.getByText(/This alert is closed/)).toBeVisible();
  await expect(
    page.getByText('Version 2 · false positive', { exact: true }),
  ).toBeVisible();
});

test('detail errors and tablet layout remain accessible', async ({ page }) => {
  await setup(page);
  await page.setViewportSize({ width: 768, height: 1100 });
  await visitAuthenticated(page, `/alerts/${alertId}`);
  await expect(
    page.getByRole('heading', { name: 'Audit history' }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: 'test-results/alert-investigation-tablet.png',
    fullPage: true,
  });
  await page.route(
    `**/api/transactions/${transactionId}/investigation`,
    (route) =>
      route.fulfill({
        status: 404,
        json: { error: { message: 'Transaction not found' } },
      }),
  );
  await visitAuthenticated(page, `/transactions/${transactionId}`);
  await expect(page.getByRole('alert')).toContainText('Transaction not found');
});
