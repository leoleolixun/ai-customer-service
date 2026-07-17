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
    if (path === '/v1/admin/conversations') {
      await route.fulfill({
        json: {
          items: [{
            id: '4aa7d74f-253f-4f42-8f40-c53c118dd24a',
            application_id: 'application-e2e',
            end_user_id: 'end-user-e2e',
            external_user_id: 'customer-e2e',
            mode: 'ai',
            status: 'open',
            created_at: '2026-07-17T08:00:00Z',
            updated_at: '2026-07-17T08:05:00Z',
          }],
          next_cursor: null,
          has_more: false,
        },
      });
      return;
    }
    if (path === '/v1/admin/conversations/4aa7d74f-253f-4f42-8f40-c53c118dd24a/messages') {
      await route.fulfill({
        json: {
          items: [{
            id: 'message-e2e',
            conversation_id: '4aa7d74f-253f-4f42-8f40-c53c118dd24a',
            sender: 'ai',
            content: '这是依据知识库生成的客服回复。',
            status: 'completed',
            error_code: null,
            citations: [{
              id: 'citation-e2e',
              source_title: '测试知识文档',
              source_url: 'https://docs.example.test/source',
              quote: '这是可以核对的来源片段。',
            }],
            model_info: { model: 'glm-4-flash', grounding: 'evidence', evidence_count: 1 },
            created_at: '2026-07-17T08:05:00Z',
            updated_at: '2026-07-17T08:05:00Z',
          }],
          next_cursor: null,
          has_more: false,
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

  await page.getByRole('button', { name: 'Change language' }).click();
  await page.getByRole('menuitem', { name: '简体中文' }).click();
  await page.getByRole('button', { name: '会话记录' }).click();

  await expect(page).toHaveURL('http://127.0.0.1:5173/conversations');
  await expect(page.getByRole('heading', { name: '会话记录' })).toBeVisible();
  await expect(page.getByRole('button', { name: /customer-e2e/ })).toBeVisible();
  await expect(page.getByText('这是依据知识库生成的客服回复。')).toBeVisible();
  await expect(page.getByText('引用来源')).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('lang', 'zh-CN');
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

  await expect(page.getByRole('alert')).toContainText('The email or password is incorrect.');
  await expect(page.getByRole('button', { name: 'Sign in' })).toBeEnabled();
  await expect.poll(() => page.evaluate(() => localStorage.getItem('support-admin-token')))
    .toBeNull();
});
