import type { StreamEvent } from './types';

export async function* parseSSE(
  stream: ReadableStream<Uint8Array>,
): AsyncGenerator<StreamEvent> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  try {
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      const blocks = buffer.split(/\r?\n\r?\n/);
      buffer = blocks.pop() ?? '';
      for (const block of blocks) {
        const event = parseBlock(block);
        if (event) yield event;
      }
      if (done) break;
    }
    if (buffer.trim()) {
      const event = parseBlock(buffer);
      if (event) yield event;
    }
  } finally {
    reader.releaseLock();
  }
}

function parseBlock(block: string): StreamEvent | null {
  let eventType = '';
  const dataLines: string[] = [];
  for (const line of block.split(/\r?\n/)) {
    if (line.startsWith('event:')) eventType = line.slice(6).trim();
    if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart());
  }
  if (!eventType || dataLines.length === 0) return null;
  const data: unknown = JSON.parse(dataLines.join('\n'));
  if (!isEventType(eventType)) return null;
  return { type: eventType, data } as StreamEvent;
}

function isEventType(value: string): value is StreamEvent['type'] {
  return [
    'message.started',
    'message.delta',
    'message.completed',
    'message.error',
  ].includes(value);
}
