import { expect, test, type Route } from '@playwright/test';

test('widget renders an explicit no-evidence refusal without a fabricated citation', async ({
  page,
}) => {
  await page.route('**/api/support-token', (route) =>
    route.fulfill({ json: { access_token: 'refusal-customer-token' } }),
  );
  await page.route('**/v1/**', async (route) => handleRoute(route));

  await page.goto('http://127.0.0.1:5174');
  await page.getByRole('button', { name: 'Open support' }).click();
  await page.getByRole('textbox', { name: 'Message' }).fill('What is the CEO private phone number?');
  await page.getByRole('button', { name: 'Send message' }).click();

  await expect(
    page.getByText('The current knowledge base does not contain enough reliable information.'),
  ).toBeVisible();
  await expect(page.getByLabel('Sources')).toHaveCount(0);
});

async function handleRoute(route: Route): Promise<void> {
  const request = route.request();
  const path = new URL(request.url()).pathname;
  if (path === '/v1/chat/sessions' && request.method() === 'POST') {
    await route.fulfill({
      json: {
        id: 'conversation-refusal',
        application_id: 'demo',
        mode: 'ai',
        status: 'open',
        created_at: '2026-07-17T00:00:00Z',
        updated_at: '2026-07-17T00:00:00Z',
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
    await route.fulfill({ json: { code: 'handoff_not_found', detail: 'Not found' }, status: 404 });
    return;
  }
  if (path.endsWith('/messages') && request.method() === 'POST') {
    const content = 'The current knowledge base does not contain enough reliable information.';
    const completed = {
      id: 'message-refusal',
      conversation_id: 'conversation-refusal',
      sender: 'ai',
      content,
      status: 'completed',
      error_code: null,
      citations: [],
      created_at: '2026-07-17T00:00:00Z',
      updated_at: '2026-07-17T00:00:00Z',
    };
    await route.fulfill({
      body: [
        'event: message.started\ndata: {"message_id":"message-refusal","replay":false}',
        `event: message.delta\ndata: ${JSON.stringify({ delta: content })}`,
        `event: message.completed\ndata: ${JSON.stringify(completed)}`,
        '',
      ].join('\n\n'),
      contentType: 'text/event-stream',
    });
    return;
  }
  await route.fulfill({ json: { code: 'unexpected_route', detail: path }, status: 500 });
}
