import { expect, type Page } from '@playwright/test';

export const testToken = 'test-only-access-token-with-at-least-32-characters';
export async function visitAuthenticated(page: Page, path: string) {
  await page.route('**/api/auth/me', (route) => route.fulfill({json: {username: 'operator-17', role: 'operator'}}));
  await page.goto(path);
  await signIn(page);
}

export async function signIn(page: Page) {
  await page.getByLabel('Access token').fill(testToken);
  await page.getByRole('button', {name: 'Sign in', exact: true}).click();
  await expect(page.getByRole('button', {name: 'Sign out'})).toBeVisible();
}
