import { expect, test } from '@playwright/test';

const now = '2026-07-17T00:00:00Z';

test('mobile agent accepts, replies to, and closes a handoff in Simplified Chinese', async ({
  page,
}) => {
  const staffId = 'mobile-agent';
  let status: 'pending' | 'accepted' | 'closed' = 'pending';
  const messages = [message('mobile-customer', 'user', '我需要人工客服。')];
  await page.addInitScript(() => {
    localStorage.setItem('support-admin-token', 'mobile-agent-token');
    localStorage.setItem('ai-support.language', 'zh-CN');
  });
  await page.route('**/v1/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === '/v1/admin/me') {
      await route.fulfill({
        json: {
          id: staffId,
          email: 'mobile-agent@example.test',
          is_platform_admin: false,
          tenant_id: 'tenant-mobile',
          role: 'agent',
        },
      });
      return;
    }
    if (path === '/v1/admin/handoffs' && request.method() === 'GET') {
      await route.fulfill({ json: status === 'closed' ? [] : [handoff(status, staffId)] });
      return;
    }
    if (path.endsWith('/messages') && request.method() === 'GET') {
      await route.fulfill({ json: messages });
      return;
    }
    if (path.endsWith('/accept') && request.method() === 'POST') {
      status = 'accepted';
      await route.fulfill({ json: handoff(status, staffId) });
      return;
    }
    if (path.endsWith('/messages') && request.method() === 'POST') {
      const body = request.postDataJSON() as { content: string };
      const reply = message('mobile-agent-reply', 'agent', body.content);
      messages.push(reply);
      await route.fulfill({ json: reply, status: 201 });
      return;
    }
    if (path.endsWith('/close') && request.method() === 'POST') {
      status = 'closed';
      await route.fulfill({ json: handoff(status, staffId) });
      return;
    }
    await route.fulfill({ json: [] });
  });

  await page.goto('http://127.0.0.1:5173/handoffs');
  await expect(page.getByRole('heading', { name: '客服工作台' })).toBeVisible();
  await expect(page.getByText('客户申请人工客服').first()).toBeVisible();
  await page.getByRole('button', { name: '接入' }).click();

  const reply = page.getByPlaceholder('回复客户');
  await expect(reply).toBeEnabled();
  await reply.fill('人工客服已接入。');
  await page.getByRole('button', { name: '发送回复' }).click();
  await expect(page.getByText('人工客服已接入。')).toBeVisible();

  await page.getByRole('button', { name: '关闭', exact: true }).click();
  await expect(page.getByText('暂无活动的人工转接')).toBeVisible();
  await expect(page.getByPlaceholder('回复客户')).toHaveCount(0);
});

function handoff(status: 'pending' | 'accepted' | 'closed', staffId: string) {
  return {
    id: 'handoff-mobile-agent',
    application_id: 'demo',
    conversation_id: 'conversation-mobile-agent',
    assigned_staff_user_id: status === 'pending' ? null : staffId,
    status,
    reason: 'customer_requested_handoff',
    summary: '客户：我需要人工客服。',
    accepted_at: status === 'pending' ? null : now,
    closed_at: status === 'closed' ? now : null,
    close_reason: status === 'closed' ? 'resolved' : null,
    created_at: now,
    updated_at: now,
  };
}

function message(id: string, sender: 'user' | 'agent', content: string) {
  return {
    id,
    conversation_id: 'conversation-mobile-agent',
    sender,
    content,
    status: 'completed',
    error_code: null,
    citations: [],
    created_at: now,
    updated_at: now,
  };
}
