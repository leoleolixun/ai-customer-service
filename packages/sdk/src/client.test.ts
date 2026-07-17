import { describe, expect, it, vi } from 'vitest';

import { SupportClient } from './client';

describe('SupportClient locale', () => {
  it('sends the selected locale with streamed messages', async () => {
    const request = vi.fn<typeof fetch>().mockResolvedValue(new Response(
      'event: message.error\ndata: {"code":"done","message":"done"}\n\n',
      { headers: { 'Content-Type': 'text/event-stream' } },
    ));
    const client = new SupportClient({
      baseUrl: 'https://support.example.test',
      getToken: () => 'customer-token',
      getLocale: () => 'zh-CN',
      fetch: request,
    });

    for await (const _event of client.streamMessage('conversation-1', '你好', 'message-1')) {
      // Consume the mocked stream so the request body can be asserted.
    }

    const init = request.mock.calls[0]?.[1];
    expect(JSON.parse(String(init?.body))).toEqual({ content: '你好', locale: 'zh-CN' });
  });

  it('defaults to English for existing integrations', async () => {
    const request = vi.fn<typeof fetch>().mockResolvedValue(new Response(
      'event: message.error\ndata: {"code":"done","message":"done"}\n\n',
      { headers: { 'Content-Type': 'text/event-stream' } },
    ));
    const client = new SupportClient({
      baseUrl: 'https://support.example.test',
      getToken: () => 'customer-token',
      fetch: request,
    });

    for await (const _event of client.streamMessage('conversation-1', 'Hello', 'message-1')) {
      // Consume the mocked stream so the request body can be asserted.
    }

    const init = request.mock.calls[0]?.[1];
    expect(JSON.parse(String(init?.body))).toEqual({ content: 'Hello', locale: 'en' });
  });
});
