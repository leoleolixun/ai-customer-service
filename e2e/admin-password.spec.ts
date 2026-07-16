import { expect, test } from '@playwright/test';

test('staff changes the temporary password and is signed out', async ({ page }) => {
  let submitted: Record<string, string> | null = null;
  await page.addInitScript(() => {
    localStorage.setItem('support-admin-token', 'temporary-session-token');
  });
  await page.route('**/v1/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === '/v1/admin/me') {
      await route.fulfill({
        json: {
          id: 'staff-password-e2e',
          email: 'admin@example.test',
          is_platform_admin: false,
          tenant_id: 'tenant-e2e',
          role: 'tenant_admin',
        },
      });
      return;
    }
    if (path === '/v1/admin/auth/change-password' && request.method() === 'POST') {
      submitted = request.postDataJSON() as Record<string, string>;
      await route.fulfill({ status: 204 });
      return;
    }
    if (path === '/v1/admin/usage/summary') {
      await route.fulfill({
        json: {
          from_at: '2026-06-17T00:00:00Z',
          to_at: '2026-07-17T00:00:00Z',
          application_id: null,
          total_requests: 0,
          completed_requests: 0,
          failed_requests: 0,
          prompt_tokens: 0,
          completion_tokens: 0,
          average_duration_ms: 0,
          estimated_cost_micros: 0,
        },
      });
      return;
    }
    await route.fulfill({ json: [] });
  });

  await page.goto('http://127.0.0.1:5173/');
  await page.getByRole('button', { name: 'Change password' }).click();
  await page.getByLabel('Current password').fill('temporary-password');
  await page.getByLabel('New password', { exact: true }).fill('replacement-password');
  await page.getByLabel('Confirm new password').fill('replacement-password');
  await page.getByRole('button', { name: 'Change password', exact: true }).last().click();

  await expect(page).toHaveURL('http://127.0.0.1:5173/login');
  await expect.poll(() => submitted).toEqual({
    current_password: 'temporary-password',
    new_password: 'replacement-password',
  });
  await expect.poll(() => page.evaluate(() => localStorage.getItem('support-admin-token')))
    .toBeNull();
});
