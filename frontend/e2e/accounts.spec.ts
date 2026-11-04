import { test, expect } from "./fixtures";

test("administrator creates a viewer whose review and mutation controls are restricted", async ({ page }) => {
  const session = await (await page.request.get('/api/auth/me')).json();
  const headers = { 'X-CSRF-Token': session.csrf_token };
  const sample = (await (await page.request.get('/api/samples')).json()).items[0];
  const incident = await (await page.request.post('/api/incidents', { headers, data: { title: 'Viewer review fixture', error_log: sample.error_log } })).json();
  await page.request.post(`/api/incidents/${incident.id}/investigate`, { headers, data: {} });
  await expect.poll(async () => (await (await page.request.get(`/api/incidents/${incident.id}`)).json()).status).toBe('awaiting_review');
  await page.goto('/settings');
  const username = `reader-${Date.now()}`;
  await page.getByLabel('New username', { exact: true }).fill(username);
  await page.getByLabel('Temporary password', { exact: true }).fill('browser-viewer-password-only');
  await page.getByRole('button', { name: 'Create account', exact: true }).click();
  await expect(page.getByText(username, { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Sign out', exact: true }).click();
  await page.getByLabel('Username', { exact: true }).fill(username);
  await page.getByLabel('Password', { exact: true }).fill('browser-viewer-password-only');
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Sign out' })).toBeVisible();
  await page.goto(`/investigations/${incident.id}/review`);
  await expect(page.getByText('Viewer access.', { exact: false })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Approve fix', exact: true })).toHaveCount(0);
  await page.goto('/investigations/new');
  await expect(page.getByRole('heading', { name: 'Read-only access' })).toBeVisible();
  await page.goto('/settings');
  await expect(page.getByRole('button', { name: 'Save configuration' })).toBeDisabled();
});
