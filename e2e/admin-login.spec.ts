import { expect, test } from '@playwright/test';

test('admin console persists the selected Simplified Chinese language', async ({ page }) => {
  await page.goto('http://127.0.0.1:5173/login');

  await page.getByRole('button', { name: 'Change language' }).click();
  await page.getByRole('menuitem', { name: '简体中文' }).click();

  await expect(page.getByRole('heading', { name: '客服管理后台' })).toBeVisible();
  await expect(page.getByRole('button', { name: '登录' })).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('lang', 'zh-CN');
  await expect.poll(() => page.evaluate(() => localStorage.getItem('ai-support.language')))
    .toBe('zh-CN');

  await page.reload();
  await expect(page.getByRole('heading', { name: '客服管理后台' })).toBeVisible();
  await expect(page.getByRole('textbox', { name: '邮箱' })).toBeVisible();
});

test('staff can sign in and reach the tenant overview', async ({ page }) => {
  await page.route('**/v1/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === '/v1/admin/auth/login') {
      await route.fulfill({ json: { access_token: 'e2e-admin-token' } });
      return;
    }
    if (path === '/v1/admin/me') {
      await route.fulfill({
        json: {
          id: 'staff-e2e',
          email: 'admin@example.test',
          is_platform_admin: false,
          tenant_id: 'tenant-e2e',
          role: 'tenant_admin',
        },
      });
      return;
    }
    if (path === '/v1/admin/usage/summary') {
      await route.fulfill({
        json: {
          from_at: '2026-06-17T00:00:00Z',
          to_at: '2026-07-17T00:00:00Z',
          application_id: null,
          total_requests: 4,
          completed_requests: 4,
          failed_requests: 0,
          prompt_tokens: 10,
          completion_tokens: 20,
          average_duration_ms: 120,
          estimated_cost_micros: 0,
        },
      });
      return;
    }
    await route.fulfill({ json: [] });
  });

  await page.goto('http://127.0.0.1:5173/login');
  await page.getByRole('textbox', { name: 'Email' }).fill('admin@example.test');
  await page.getByLabel('Password').fill('correct-password');
  await page.getByRole('textbox', { name: 'Tenant ID' }).fill('tenant-e2e');
  await page.getByRole('button', { name: 'Sign in' }).click();

  await expect(page).toHaveURL('http://127.0.0.1:5173/');
  await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible();
  await expect(page.getByRole('main').getByText('Applications')).toBeVisible();
  await expect.poll(() => page.evaluate(() => localStorage.getItem('support-admin-token')))
    .toBe('e2e-admin-token');
});

test('staff login surfaces Problem Details without storing a token', async ({ page }) => {
  await page.route('**/v1/admin/auth/login', (route) =>
    route.fulfill({
      json: { code: 'invalid_credentials', detail: 'Invalid email or password' },
      status: 401,
    }),
  );
  await page.goto('http://127.0.0.1:5173/login');

  await page.getByRole('textbox', { name: 'Email' }).fill('admin@example.test');
  await page.getByLabel('Password').fill('wrong-password');
  await page.getByRole('button', { name: 'Sign in' }).click();

  await expect(page.getByRole('alert')).toContainText('Invalid email or password');
  await expect(page.getByRole('button', { name: 'Sign in' })).toBeEnabled();
  await expect.poll(() => page.evaluate(() => localStorage.getItem('support-admin-token')))
    .toBeNull();
});
