import { expect, test, type Page } from '@playwright/test';

const now = '2026-07-17T00:00:00Z';

test('widget requests a handoff and sends follow-up messages without invoking AI', async ({
  page,
}) => {
  let handoffRequested = false;
  let humanMessageRequests = 0;
  await page.route('**/api/support-token', (route) =>
    route.fulfill({ json: { access_token: 'handoff-customer-token' } }),
  );
  await page.route('**/v1/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === '/v1/chat/sessions' && request.method() === 'POST') {
      await route.fulfill({
        json: {
          id: 'conversation-handoff',
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
    if (path.endsWith('/messages') && request.method() === 'GET') {
      await route.fulfill({ json: [] });
      return;
    }
    if (path.endsWith('/handoff') && request.method() === 'GET') {
      await route.fulfill({
        json: { code: 'handoff_not_found', detail: 'Not found' },
        status: 404,
      });
      return;
    }
    if (path.endsWith('/handoff') && request.method() === 'POST') {
      handoffRequested = true;
      await route.fulfill({ json: handoff('pending', null), status: 201 });
      return;
    }
    if (path.endsWith('/human-messages') && request.method() === 'POST') {
      humanMessageRequests += 1;
      const body = request.postDataJSON() as { content: string };
      await route.fulfill({
        json: message('customer-follow-up', 'user', body.content),
        status: 201,
      });
      return;
    }
    await route.fulfill({ json: { code: 'unexpected_route', detail: path }, status: 500 });
  });

  await page.goto('http://127.0.0.1:5174');
  await page.getByRole('button', { name: 'Open support' }).click();
  await page.getByRole('button', { name: 'Contact an agent' }).click();

  await expect(page.getByText('Waiting for an agent').first()).toBeVisible();
  await page.getByRole('textbox', { name: 'Message' }).fill('My order number is DEMO-123.');
  await page.getByRole('button', { name: 'Send message' }).click();

  await expect(page.getByText('My order number is DEMO-123.')).toBeVisible();
  expect(handoffRequested).toBe(true);
  await expect.poll(() => humanMessageRequests).toBe(1);
});

test('agent accepts, replies to, and closes one active handoff', async ({ page }) => {
  const staffId = 'staff-agent-e2e';
  let currentHandoff = handoff('pending', null);
  const messages = [message('customer-message', 'user', 'I need a human agent.')];
  await page.addInitScript(() => {
    localStorage.setItem('support-admin-token', 'agent-e2e-token');
  });
  await page.route('**/v1/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === '/v1/admin/me') {
      await route.fulfill({
        json: {
          id: staffId,
          email: 'agent@example.test',
          is_platform_admin: false,
          tenant_id: 'tenant-e2e',
          role: 'agent',
        },
      });
      return;
    }
    if (path === '/v1/admin/handoffs' && request.method() === 'GET') {
      await route.fulfill({ json: [currentHandoff] });
      return;
    }
    if (path.endsWith('/messages') && request.method() === 'GET') {
      await route.fulfill({ json: messages });
      return;
    }
    if (path.endsWith('/accept') && request.method() === 'POST') {
      currentHandoff = handoff('accepted', staffId);
      await route.fulfill({ json: currentHandoff });
      return;
    }
    if (path.endsWith('/messages') && request.method() === 'POST') {
      const body = request.postDataJSON() as { content: string };
      messages.push(message('agent-message', 'agent', body.content));
      await route.fulfill({ json: messages.at(-1), status: 201 });
      return;
    }
    if (path.endsWith('/close') && request.method() === 'POST') {
      currentHandoff = { ...handoff('closed', staffId), close_reason: 'resolved' };
      await route.fulfill({ json: currentHandoff });
      return;
    }
    await route.fulfill({ json: [] });
  });

  await page.goto('http://127.0.0.1:5173/handoffs');
  await expect(page.getByRole('heading', { name: 'Agent workspace' })).toBeVisible();
  await page.getByRole('button', { name: 'Accept' }).click();

  const reply = page.getByPlaceholder('Reply to customer');
  await expect(reply).toBeEnabled();
  await reply.fill('I have joined the conversation.');
  await page.getByRole('button', { name: 'Send reply' }).click();
  await expect(page.getByText('I have joined the conversation.')).toBeVisible();

  await page.getByRole('button', { name: 'Close', exact: true }).click();
  await expect(page.getByText('No active handoffs')).toBeVisible();
  await expect(page.getByPlaceholder('Reply to customer')).toHaveCount(0);
});

function handoff(
  status: 'pending' | 'accepted' | 'closed',
  assignedStaffUserId: string | null,
) {
  return {
    id: 'handoff-e2e',
    application_id: 'demo',
    conversation_id: 'conversation-handoff',
    assigned_staff_user_id: assignedStaffUserId,
    status,
    reason: 'Customer requested human support',
    summary: 'Customer: I need a human agent.',
    accepted_at: status === 'accepted' ? now : null,
    closed_at: status === 'closed' ? now : null,
    close_reason: status === 'closed' ? 'resolved' : null,
    created_at: now,
    updated_at: now,
  };
}

function message(id: string, sender: 'user' | 'agent', content: string) {
  return {
    id,
    conversation_id: 'conversation-handoff',
    sender,
    content,
    status: 'completed',
    error_code: null,
    citations: [],
    created_at: now,
    updated_at: now,
  };
}
