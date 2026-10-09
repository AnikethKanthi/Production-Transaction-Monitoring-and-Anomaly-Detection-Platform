import { expect, test } from '@playwright/test';

test('shows API health and allows another check without browser errors', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.route('**/api/health', (route) => route.fulfill({
    json: { status: 'ok', service: 'api', version: '0.1.0' },
  }));
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'A foundation for every transaction.' })).toBeVisible();
  await expect(page.getByText('API is responding · v0.1.0')).toBeVisible();
  await page.getByRole('button', { name: 'Check again' }).click();
  await expect(page.getByText('API is responding · v0.1.0')).toBeVisible();
  expect(errors).toEqual([]);
});

test('reports an unavailable API and recovers after a retry', async ({ page }) => {
  await page.route('**/api/health', (route) => route.fulfill({ status: 503, body: 'Unavailable' }));
  await page.goto('/');
  await expect(page.getByText('API unavailable.', { exact: false })).toBeVisible();
  await page.unroute('**/api/health');
  await page.route('**/api/health', (route) => route.fulfill({
    json: { status: 'ok', service: 'api', version: '0.1.0' },
  }));
  await page.getByRole('button', { name: 'Check again' }).click();
  await expect(page.getByText('API is responding · v0.1.0')).toBeVisible();
});
