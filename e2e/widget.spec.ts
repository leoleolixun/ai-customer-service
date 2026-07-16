import { expect, test, type Page, type Route } from '@playwright/test';

const now = '2026-07-17T00:00:00Z';

async function mockWidgetApi(page: Page): Promise<void> {
  await page.route('**/api/support-token', (route) =>
    route.fulfill({ json: { access_token: 'e2e-customer-token' } }),
  );
  await page.route('**/v1/**', async (route) => handleWidgetRoute(route));
}

async function handleWidgetRoute(route: Route): Promise<void> {
  const request = route.request();
  const path = new URL(request.url()).pathname;
  if (path === '/v1/chat/sessions' && request.method() === 'POST') {
    await route.fulfill({
      json: {
        id: 'conversation-e2e',
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
  if (path.endsWith('/messages') && request.method() === 'POST') {
    const completed = {
      id: 'message-ai-e2e',
      conversation_id: 'conversation-e2e',
      sender: 'ai',
      content: 'You can reset your password from Account settings.',
      status: 'completed',
      error_code: null,
      citations: [
        {
          id: 'citation-e2e',
          document_id: 'document-e2e',
          chunk_id: 'chunk-e2e',
          quote: 'Open Account settings and choose Reset password.',
          source_title: 'Password guide',
          source_url: 'https://docs.example.test/password',
          score: 0.96,
        },
      ],
      created_at: now,
      updated_at: now,
    };
    const body = [
      'event: message.started\ndata: {"message_id":"message-ai-e2e","replay":false}',
      'event: message.delta\ndata: {"delta":"You can reset your password from Account settings."}',
      `event: message.completed\ndata: ${JSON.stringify(completed)}`,
      '',
    ].join('\n\n');
    await route.fulfill({
      body,
      contentType: 'text/event-stream',
      status: 200,
    });
    return;
  }
  await route.fulfill({ json: { code: 'not_mocked', detail: path }, status: 500 });
}

test('help center opens the widget and renders a cited SSE response', async ({ page }) => {
  await mockWidgetApi(page);
  await page.goto('http://127.0.0.1:5174');

  await expect(page.getByRole('heading', { name: 'How can we help?' })).toBeVisible();
  await page.getByRole('button', { name: 'Open support' }).click();
  await expect(page.getByRole('dialog', { name: 'Northstar Support' })).toBeVisible();
  await expect(page.getByText('Ask a question about your Northstar account.')).toBeVisible();

  await page.getByRole('textbox', { name: 'Message' }).fill('How do I reset my password?');
  await page.getByRole('button', { name: 'Send message' }).click();

  await expect(page.getByText('You can reset your password from Account settings.')).toBeVisible();
  await expect(page.getByRole('link', { name: 'Password guide' })).toHaveAttribute(
    'href',
    'https://docs.example.test/password',
  );
});
