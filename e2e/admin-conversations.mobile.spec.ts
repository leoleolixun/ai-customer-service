import { expect, test } from '@playwright/test';

const conversationId = 'd7c0d0c5-8e04-4b6c-93a3-64251b28aaf1';
const now = '2026-07-17T08:00:00Z';

test('mobile agent switches language and reviews a cited conversation without overflow', async ({
  page,
}) => {
  await page.addInitScript(() => {
    localStorage.setItem('support-admin-token', 'mobile-admin-token');
    if (!localStorage.getItem('ai-support.language')) {
      localStorage.setItem('ai-support.language', 'en');
    }
  });
  await page.route('**/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === '/v1/admin/me') {
      await route.fulfill({
        json: {
          id: 'mobile-admin',
          email: 'mobile-admin@example.test',
          is_platform_admin: false,
          tenant_id: 'tenant-mobile',
          role: 'agent',
        },
      });
      return;
    }
    if (path === '/v1/admin/applications') {
      await route.fulfill({
        json: [{
          id: 'application-mobile',
          tenant_id: 'tenant-mobile',
          name: 'Mobile help center',
          public_key: 'pk_mobile',
          allowed_origins: [],
          rate_limit_per_minute: 60,
          status: 'active',
          created_at: now,
          updated_at: now,
        }],
      });
      return;
    }
    if (path === '/v1/admin/conversations') {
      await route.fulfill({
        json: {
          items: [{
            id: conversationId,
            application_id: 'application-mobile',
            end_user_id: 'end-user-mobile',
            external_user_id: 'mobile-customer',
            mode: 'ai',
            status: 'open',
            created_at: now,
            updated_at: now,
          }],
          next_cursor: null,
          has_more: false,
        },
      });
      return;
    }
    if (path === `/v1/admin/conversations/${conversationId}/messages`) {
      await route.fulfill({
        json: {
          items: [{
            id: 'message-mobile-admin',
            conversation_id: conversationId,
            sender: 'ai',
            content: '可以在账户设置中重置密码。',
            status: 'completed',
            error_code: null,
            citations: [{
              id: 'citation-mobile-admin',
              source_title: '密码指南',
              source_url: 'https://docs.example.test/password',
              quote: '打开账户设置并选择重置密码。',
            }],
            model_info: { model: 'glm-4-flash', grounding: 'evidence', evidence_count: 1 },
            created_at: now,
            updated_at: now,
          }, {
            id: 'message-mobile-failed',
            conversation_id: conversationId,
            sender: 'ai',
            content: '',
            status: 'failed',
            error_code: 'model_provider_failed',
            citations: [],
            model_info: {},
            created_at: now,
            updated_at: now,
          }],
          next_cursor: null,
          has_more: false,
        },
      });
      return;
    }
    await route.fulfill({ json: [] });
  });

  await page.goto('http://127.0.0.1:5173/conversations');
  await expect(page.getByRole('heading', { name: 'Conversations' })).toBeVisible();

  await page.getByRole('button', { name: 'Open navigation' }).click();
  await expect(page.getByRole('button', { name: 'Conversations', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Agent workspace', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Conversations', exact: true }).click();

  await page.getByRole('button', { name: 'Change language' }).click();
  await page.getByRole('menuitem', { name: '简体中文' }).click();
  await expect(page.getByRole('heading', { name: '会话记录' })).toBeVisible();
  await expect(page.getByText('可以在账户设置中重置密码。')).toBeVisible();
  await expect(page.getByText('这条 AI 回复生成失败。')).toBeVisible();
  await expect(page.getByText('原因：模型 Provider 请求失败。')).toBeVisible();
  await expect(page.getByRole('link', { name: /打开来源/ })).toHaveAttribute(
    'href',
    'https://docs.example.test/password',
  );
  await expect.poll(() => page.evaluate(() => localStorage.getItem('ai-support.language')))
    .toBe('zh-CN');

  const horizontalOverflow = await page.evaluate(
    () => document.documentElement.scrollWidth - window.innerWidth,
  );
  expect(horizontalOverflow).toBeLessThanOrEqual(0);

  await page.reload();
  await expect(page.getByRole('heading', { name: '会话记录' })).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('lang', 'zh-CN');
});
