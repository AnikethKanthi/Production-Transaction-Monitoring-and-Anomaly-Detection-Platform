import { expect, test } from '@playwright/test';
import { testToken, visitAuthenticated } from './auth-helper';

test.beforeEach(async ({page}) => {
  await page.route('**/api/health', route => route.fulfill({json: {status: 'ok', service: 'api', version: '1.0.0'}}));
  await page.route('**/api/transactions?*', route => route.fulfill({json: {items: [], pagination: {limit: 20, offset: 0, total: 0}}}));
});

test('protected content requires sign-in and token stays out of browser storage', async ({page}) => {
  await page.route('**/api/auth/me', route => {
    expect(route.request().headers().authorization).toBe(`Bearer ${testToken}`);
    return route.fulfill({json: {username: 'operator-17', role: 'operator'}});
  });
  await page.route('**/api/alerts?*', route => {
    expect(route.request().headers().authorization).toBe(`Bearer ${testToken}`);
    return route.fulfill({json: {items: [], pagination: {limit: 20, offset: 0, total: 0}}});
  });
  await page.goto('/alerts');
  await page.setViewportSize({width: 768, height: 1024});
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({path: 'test-results/sign-in-tablet.png', fullPage: true});
  await expect(page.getByRole('heading', {name: 'Sign in to monitoring'})).toBeVisible();
  await expect(page.getByRole('navigation')).toHaveCount(0);
  await page.getByLabel('Access token').fill(testToken);
  await page.getByRole('button', {name: 'Sign in', exact: true}).click();
  await expect(page.getByRole('button', {name: 'Sign out'})).toBeVisible();
  expect(await page.evaluate(() => JSON.stringify({...localStorage, ...sessionStorage})) ).not.toContain(testToken);
  expect(page.url()).not.toContain(testToken);
  await page.getByRole('button', {name: 'Sign out'}).click();
  await expect(page.getByRole('heading', {name: 'Sign in to monitoring'})).toBeVisible();
  await expect(page.getByLabel('Access token')).toBeEmpty();
});

test('invalid token gives a safe sign-in error and refresh drops identity', async ({page}) => {
  await page.route('**/api/auth/me', route => route.fulfill({status: 401, json: {error: {message: 'Invalid token'}}}));
  await page.goto('/transactions');
  await page.getByLabel('Access token').fill(testToken);
  await page.getByRole('button', {name: 'Sign in', exact: true}).click();
  await expect(page.getByRole('alert')).toContainText('Sign-in failed');
  await expect(page.getByLabel('Access token')).toBeEmpty();
  await visitAuthenticated(page, '/transactions');
  await page.reload();
  await expect(page.getByRole('heading', {name: 'Sign in to monitoring'})).toBeVisible();
});

test('401 from protected API signs out and hides cached data', async ({page}) => {
  await page.route('**/api/alerts?*', route => route.fulfill({status: 401, json: {error: {message: 'Unauthorized'}}}));
  await visitAuthenticated(page, '/not-a-real-route');
  await page.getByRole('link', {name: /Alerts/}).click();
  await expect(page.getByRole('heading', {name: 'Sign in to monitoring'})).toBeVisible();
  await expect(page.getByRole('alert')).toContainText('no longer authorized');
});
