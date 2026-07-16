import {
  ArrowRight,
  ChevronRight,
  Compass,
  ReceiptText,
  Search,
  UserRound,
  Users,
  createIcons,
} from 'lucide';

import '@ai-support/widget';
import type { AISupportWidgetElement } from '@ai-support/widget';

const widget = document.querySelector<AISupportWidgetElement>('#support-widget');
if (widget) {
  widget.setAttribute(
    'base-url',
    import.meta.env.VITE_SUPPORT_BASE_URL ?? widget.getAttribute('base-url') ?? window.location.origin,
  );
  widget.setAttribute(
    'application-id',
    import.meta.env.VITE_SUPPORT_APPLICATION_ID ?? widget.getAttribute('application-id') ?? 'demo',
  );
  widget.setAttribute('session-key', 'northstar-demo-user');
  widget.tokenProvider = async () => {
    const response = await fetch(import.meta.env.VITE_SUPPORT_TOKEN_ENDPOINT ?? '/api/support-token', {
      credentials: 'include',
    });
    if (!response.ok || !response.headers.get('content-type')?.includes('application/json')) {
      throw new Error('The demo support token endpoint is not configured.');
    }
    const body = (await response.json()) as { access_token: string };
    if (!body.access_token) throw new Error('The support token response is invalid.');
    return body.access_token;
  };
}

const search = document.querySelector<HTMLInputElement>('#article-search');
const topics = Array.from(document.querySelectorAll<HTMLElement>('[data-search]'));
search?.addEventListener('input', () => {
  const query = search.value.trim().toLowerCase();
  topics.forEach((topic) => {
    topic.hidden = Boolean(query) && !topic.dataset.search?.includes(query);
  });
});

createIcons({
  icons: { ArrowRight, ChevronRight, Compass, ReceiptText, Search, UserRound, Users },
});
