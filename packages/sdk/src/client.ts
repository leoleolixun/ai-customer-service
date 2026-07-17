import { parseSSE } from './sse';
import type {
  Conversation,
  Feedback,
  FeedbackRating,
  Handoff,
  Message,
  StreamEvent,
  SupportedLocale,
} from './types';

export class SupportApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId?: string;

  constructor(status: number, code: string, message: string, requestId?: string) {
    super(message);
    this.name = 'SupportApiError';
    this.status = status;
    this.code = code;
    this.requestId = requestId;
  }
}

export interface SupportClientOptions {
  baseUrl: string;
  getToken: () => string | Promise<string>;
  getLocale?: () => SupportedLocale;
  fetch?: typeof globalThis.fetch;
}

export class SupportClient {
  private readonly baseUrl: string;
  private readonly getToken: SupportClientOptions['getToken'];
  private readonly getLocale: NonNullable<SupportClientOptions['getLocale']>;
  private readonly request: typeof globalThis.fetch;

  constructor(options: SupportClientOptions) {
    this.baseUrl = options.baseUrl.replace(/\/$/, '');
    this.getToken = options.getToken;
    this.getLocale = options.getLocale ?? (() => 'en');
    this.request = options.fetch ?? globalThis.fetch.bind(globalThis);
  }

  createSession(): Promise<Conversation> {
    return this.json('/v1/chat/sessions', { method: 'POST', body: JSON.stringify({}) });
  }

  getSession(id: string): Promise<Conversation> {
    return this.json(`/v1/chat/sessions/${encodeURIComponent(id)}`);
  }

  listMessages(id: string): Promise<Message[]> {
    return this.json(`/v1/chat/sessions/${encodeURIComponent(id)}/messages`);
  }

  async getCitationSource(conversationId: string, citationId: string): Promise<Blob> {
    const response = await this.authorized(
      `/v1/chat/sessions/${encodeURIComponent(conversationId)}/citations/${encodeURIComponent(citationId)}/source`,
    );
    await this.requireOk(response);
    return response.blob();
  }

  async *streamMessage(
    conversationId: string,
    content: string,
    idempotencyKey: string = crypto.randomUUID(),
  ): AsyncGenerator<StreamEvent> {
    const response = await this.authorized(
      `/v1/chat/sessions/${encodeURIComponent(conversationId)}/messages`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Idempotency-Key': idempotencyKey },
        body: JSON.stringify({ content, locale: this.getLocale() }),
      },
    );
    await this.requireOk(response);
    if (!response.body) {
      throw new SupportApiError(502, 'stream_missing', 'The response stream is unavailable.');
    }
    yield* parseSSE(response.body);
  }

  requestHandoff(conversationId: string, reason = ''): Promise<Handoff> {
    return this.json(`/v1/chat/sessions/${encodeURIComponent(conversationId)}/handoff`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    });
  }

  getHandoff(conversationId: string): Promise<Handoff> {
    return this.json(`/v1/chat/sessions/${encodeURIComponent(conversationId)}/handoff`);
  }

  sendHumanMessage(
    conversationId: string,
    content: string,
    idempotencyKey: string = crypto.randomUUID(),
  ): Promise<Message> {
    return this.json(`/v1/chat/sessions/${encodeURIComponent(conversationId)}/human-messages`, {
      method: 'POST',
      headers: { 'Idempotency-Key': idempotencyKey },
      body: JSON.stringify({ content }),
    });
  }

  submitFeedback(
    conversationId: string,
    messageId: string,
    rating: FeedbackRating,
    comment?: string,
  ): Promise<Feedback> {
    return this.json(`/v1/chat/sessions/${encodeURIComponent(conversationId)}/feedback`, {
      method: 'POST',
      body: JSON.stringify({ message_id: messageId, rating, comment: comment || null }),
    });
  }

  private async json<T>(path: string, init: RequestInit = {}): Promise<T> {
    const response = await this.authorized(path, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...init.headers },
    });
    await this.requireOk(response);
    return (await response.json()) as T;
  }

  private async authorized(path: string, init: RequestInit = {}): Promise<Response> {
    const token = await this.getToken();
    return this.request(`${this.baseUrl}${path}`, {
      ...init,
      headers: { Authorization: `Bearer ${token}`, ...init.headers },
    });
  }

  private async requireOk(response: Response): Promise<void> {
    if (response.ok) return;
    let body: Record<string, unknown> = {};
    try {
      body = (await response.json()) as Record<string, unknown>;
    } catch {
      // Preserve the HTTP status if the upstream did not return Problem Details.
    }
    throw new SupportApiError(
      response.status,
      typeof body.code === 'string' ? body.code : 'http_error',
      typeof body.detail === 'string' ? body.detail : `Request failed with ${response.status}`,
      typeof body.request_id === 'string' ? body.request_id : undefined,
    );
  }
}
