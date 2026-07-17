import { en, zhCN } from '@/i18n/messages';

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, '') ?? '';

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly requestId?: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = localStorage.getItem('support-admin-token');
  const isFormData = init.body instanceof FormData;
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init.headers,
    },
  });
  if (!response.ok) {
    let body: Record<string, unknown> = {};
    try {
      body = (await response.json()) as Record<string, unknown>;
    } catch {
      // Preserve HTTP context for non-Problem responses.
    }
    if (response.status === 401 && token) {
      localStorage.removeItem('support-admin-token');
      window.dispatchEvent(new Event('support-auth-expired'));
    }
    throw new ApiError(
      response.status,
      typeof body.code === 'string' ? body.code : 'http_error',
      typeof body.detail === 'string' ? body.detail : `Request failed with ${response.status}`,
      typeof body.request_id === 'string' ? body.request_id : undefined,
    );
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export function errorMessage(
  error: unknown,
  fallback = 'The request could not be completed.',
  localizedMessages: Readonly<Record<string, string>> = {},
): string {
  if (error instanceof ApiError) {
    const pageMessages = document.documentElement.lang === 'zh-CN' ? zhCN.errors : en.errors;
    return localizedMessages[error.code]
      ?? (pageMessages as Readonly<Record<string, string>>)[error.code]
      ?? fallback;
  }
  return fallback;
}
