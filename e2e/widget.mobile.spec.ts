import { expect, test } from '@playwright/test';

const now = '2026-07-17T00:00:00Z';

test('mobile widget completes cited chat, refusal, and handoff without overflow', async ({ page }) => {
  let activeHandoff = false;
  await page.route('**/api/support-token', (route) =>
    route.fulfill({ json: { access_token: 'e2e-customer-token' } }),
  );
  await page.route('**/v1/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === '/v1/chat/sessions' && request.method() === 'POST') {
      await route.fulfill({
        json: {
          id: 'conversation-mobile',
          application_id: 'demo',
          mode: 'ai',
          status: 'open',
          created_at: now,
          updated_at: now,
        },
        status: 201,
      });
      return;
    }
    if (path.endsWith('/human-messages') && request.method() === 'POST') {
      const body = request.postDataJSON() as { content: string };
      await route.fulfill({ json: customerMessage('mobile-human-message', body.content), status: 201 });
      return;
    }
    if (path.endsWith('/messages') && request.method() === 'GET') {
      await route.fulfill({ json: [] });
      return;
    }
    if (path.endsWith('/messages') && request.method() === 'POST') {
      const body = request.postDataJSON() as { content: string; locale: string };
      const refused = body.content.includes('私人电话');
      const content = refused
        ? '当前知识库没有足够的可靠信息来回答这个问题。'
        : '请在账户设置中重置密码。';
      const completed = {
        ...customerMessage(refused ? 'mobile-refusal' : 'mobile-answer', content),
        sender: 'ai',
        citations: refused ? [] : [{
          id: 'mobile-citation',
          document_id: 'mobile-document',
          chunk_id: 'mobile-chunk',
          quote: '打开账户设置并选择重置密码。',
          source_title: '密码指南',
          source_url: 'https://docs.example.test/password',
          score: 0.96,
        }],
      };
      await route.fulfill({
        body: [
          `event: message.started\ndata: ${JSON.stringify({ message_id: completed.id, replay: false })}`,
          `event: message.delta\ndata: ${JSON.stringify({ delta: content })}`,
          `event: message.completed\ndata: ${JSON.stringify(completed)}`,
          '',
        ].join('\n\n'),
        contentType: 'text/event-stream',
      });
      return;
    }
    if (path.endsWith('/handoff') && request.method() === 'POST') {
      activeHandoff = true;
      await route.fulfill({ json: handoff(), status: 201 });
      return;
    }
    if (path.endsWith('/handoff') && request.method() === 'GET' && activeHandoff) {
      await route.fulfill({ json: handoff() });
      return;
    }
    await route.fulfill({ json: { code: 'handoff_not_found', detail: 'Not found' }, status: 404 });
  });

  await page.goto('http://127.0.0.1:5174');
  await page.locator('#language-select').selectOption('zh-CN');
  await page.getByRole('button', { name: '打开客服' }).click();
  const dialog = page.getByRole('dialog', { name: 'Northstar 客户支持' });
  await expect(dialog).toBeVisible();
  await expect(dialog).toHaveAttribute('aria-modal', 'false');

  const measurements = await dialog.evaluate((element) => {
    const rect = element.getBoundingClientRect();
    const style = getComputedStyle(element);
    return {
      borderRadius: style.borderRadius,
      height: Math.round(rect.height),
      width: Math.round(rect.width),
      viewportHeight: window.innerHeight,
      viewportWidth: window.innerWidth,
      horizontalOverflow: document.documentElement.scrollWidth - window.innerWidth,
    };
  });

  expect(measurements.borderRadius).toBe('0px');
  expect(Math.abs(measurements.width - measurements.viewportWidth)).toBeLessThanOrEqual(1);
  expect(Math.abs(measurements.height - measurements.viewportHeight)).toBeLessThanOrEqual(1);
  expect(measurements.horizontalOverflow).toBeLessThanOrEqual(0);
  await expect(page.getByRole('textbox', { name: '消息' })).toBeVisible();
  await expect(page.getByRole('button', { name: '关闭客服' })).toBeVisible();
  await expect(dialog.getByRole('combobox', { name: '语言' })).toHaveValue('zh-CN');

  await page.getByRole('textbox', { name: '消息' }).fill('如何重置密码？');
  await page.getByRole('button', { name: '发送消息' }).click();
  await expect(page.getByText('请在账户设置中重置密码。')).toBeVisible();
  await expect(page.getByRole('link', { name: '密码指南' })).toHaveAttribute(
    'href',
    'https://docs.example.test/password',
  );

  await page.getByRole('textbox', { name: '消息' }).fill('CEO 的私人电话是什么？');
  await page.getByRole('button', { name: '发送消息' }).click();
  const refusal = page.getByText('当前知识库没有足够的可靠信息来回答这个问题。');
  await expect(refusal).toBeVisible();
  await expect(refusal.getByRole('link')).toHaveCount(0);

  await page.getByRole('button', { name: '联系人工客服' }).click();
  await expect(page.getByText('正在等待人工客服').first()).toBeVisible();
  await page.getByRole('textbox', { name: '消息' }).fill('请由人工继续处理。');
  await page.getByRole('button', { name: '发送消息' }).click();
  await expect(page.getByText('请由人工继续处理。')).toBeVisible();
});

function customerMessage(id: string, content: string) {
  return {
    id,
    conversation_id: 'conversation-mobile',
    sender: 'user',
    content,
    status: 'completed',
    error_code: null,
    citations: [],
    created_at: now,
    updated_at: now,
  };
}

function handoff() {
  return {
    id: 'handoff-mobile',
    application_id: 'demo',
    conversation_id: 'conversation-mobile',
    assigned_staff_user_id: null,
    status: 'pending',
    reason: 'customer_requested_handoff',
    summary: 'Customer requested support.',
    accepted_at: null,
    closed_at: null,
    close_reason: null,
    created_at: now,
    updated_at: now,
  };
}
