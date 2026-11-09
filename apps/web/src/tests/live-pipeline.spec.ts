import { readFileSync } from 'node:fs';
import { expect, test } from '@playwright/test';

interface LiveContext {
  transaction_id: string;
  alert_id: string;
  token_file: string;
}

const contextPath = process.env.E2E_CONTEXT_FILE;
test.skip(!contextPath, 'Requires the Compose-backed end-to-end context');

test('generated anomaly is visible and its alert can be resolved', async ({
  page,
}) => {
  const context = JSON.parse(readFileSync(contextPath!, 'utf8')) as LiveContext;
  const token = readFileSync(context.token_file, 'utf8').trim();

  await page.goto('/');
  await page.getByLabel('Access token').fill(token);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Sign out' })).toBeVisible();
  await expect(page.getByText('Live API data')).toBeVisible();
  const anomalyChart = page.getByRole('img', { name: /Anomaly rate chart/ });
  await expect(anomalyChart).toBeVisible();
  await expect(anomalyChart).not.toHaveAttribute('aria-label', /overall 0\.0%/);

  await page.goto(`/transactions/${context.transaction_id}`);
  await expect(page.getByRole('heading', { name: 'Transaction investigation' })).toBeVisible();
  await expect(page.getByText('scored', { exact: true })).toBeVisible();
  await expect(
    page.getByRole('link', { name: /Investigate alert/ }),
  ).toBeVisible();

  await page.goto(`/alerts/${context.alert_id}`);
  await expect(page.getByRole('heading', { name: 'Alert investigation' })).toBeVisible();
  await expect(page.getByText(/meets the inclusive alert threshold/)).toBeVisible();
  await page.getByLabel('Action').selectOption('resolve');
  await page
    .getByLabel('Investigation note')
    .fill('Resolved by the Compose-backed end-to-end test');
  await page.getByRole('button', { name: 'Apply action' }).click();
  await expect(page.getByText('resolved', { exact: true }).first()).toBeVisible();
  await expect(page.getByText(/resolve/, { exact: false }).last()).toBeVisible();
});
