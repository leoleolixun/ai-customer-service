import { describe, expect, it } from 'vitest';

import { parseSSE } from './sse';

function streamFromChunks(chunks: Uint8Array[]): ReadableStream<Uint8Array> {
  return new ReadableStream<Uint8Array>({
    start(controller) {
      chunks.forEach((chunk) => controller.enqueue(chunk));
      controller.close();
    },
  });
}

async function collect(stream: ReadableStream<Uint8Array>) {
  const events = [];
  for await (const event of parseSSE(stream)) events.push(event);
  return events;
}

describe('parseSSE', () => {
  it('parses events split across arbitrary network chunks', async () => {
    const encoder = new TextEncoder();
    const parts = [
      'event: message.started\ndata: {"message_id":"m1",',
      '"replay":false}\n\nevent: message.delta\ndata: {"delta":"hello"}\n\n',
      'event: message.completed\ndata: {"id":"m1"}\n\n',
    ];
    const events = await collect(streamFromChunks(parts.map((part) => encoder.encode(part))));
    expect(events.map((event) => event.type)).toEqual([
      'message.started',
      'message.delta',
      'message.completed',
    ]);
  });

  it('preserves UTF-8 characters split inside a multi-byte code point', async () => {
    const bytes = new TextEncoder().encode(
      'event: message.delta\r\ndata: {"delta":"你好"}\r\n\r\n',
    );
    const firstMultibyteByte = bytes.findIndex((byte) => byte > 0x7f);
    const events = await collect(
      streamFromChunks([
        bytes.slice(0, firstMultibyteByte + 1),
        bytes.slice(firstMultibyteByte + 1),
      ]),
    );

    expect(events).toEqual([{ type: 'message.delta', data: { delta: '你好' } }]);
  });

  it('joins multiple data lines and parses a trailing event without a blank line', async () => {
    const body = [
      ': keep-alive',
      'event: message.delta',
      'data: {"delta":',
      'data: "hello"}',
    ].join('\n');

    await expect(collect(streamFromChunks([new TextEncoder().encode(body)]))).resolves.toEqual([
      { type: 'message.delta', data: { delta: 'hello' } },
    ]);
  });

  it('ignores comments, incomplete blocks, and unknown event types', async () => {
    const body = [
      ': heartbeat\n\n',
      'data: {"delta":"missing event"}\n\n',
      'event: custom.event\ndata: {"value":1}\n\n',
      'event: message.error\ndata: {"code":"upstream","message":"Unavailable"}\n\n',
    ].join('');

    const events = await collect(streamFromChunks([new TextEncoder().encode(body)]));

    expect(events).toEqual([
      {
        type: 'message.error',
        data: { code: 'upstream', message: 'Unavailable' },
      },
    ]);
  });

  it('rejects malformed JSON instead of yielding a partial event', async () => {
    const stream = streamFromChunks([
      new TextEncoder().encode('event: message.delta\ndata: {invalid}\n\n'),
    ]);

    await expect(collect(stream)).rejects.toThrow(SyntaxError);
  });
});
