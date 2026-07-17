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
import {
  LANGUAGE_STORAGE_KEY,
  isTranslationKey,
  matchesSearch,
  resolveLanguage,
  translate,
  type SupportedLanguage,
  type TranslationKey,
} from './i18n';

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

const languageSelect = document.querySelector<HTMLSelectElement>('#language-select');

function readStoredLanguage(): string | null {
  try {
    return window.localStorage.getItem(LANGUAGE_STORAGE_KEY);
  } catch {
    return null;
  }
}

function persistLanguage(language: SupportedLanguage): void {
  try {
    window.localStorage.setItem(LANGUAGE_STORAGE_KEY, language);
  } catch {
    // The page still switches language when storage is unavailable.
  }
}

function getTranslationKey(element: HTMLElement, attribute: string): TranslationKey | null {
  const key = element.dataset[attribute];
  return key && isTranslationKey(key) ? key : null;
}

function applyLanguage(language: SupportedLanguage): void {
  document.documentElement.lang = language;
  document.title = translate(language, 'page.title');

  document.querySelectorAll<HTMLElement>('[data-i18n]').forEach((element) => {
    const key = getTranslationKey(element, 'i18n');
    if (key) element.textContent = translate(language, key);
  });

  document.querySelectorAll<HTMLElement>('[data-i18n-aria-label]').forEach((element) => {
    const key = getTranslationKey(element, 'i18nAriaLabel');
    if (key) element.setAttribute('aria-label', translate(language, key));
  });

  document.querySelectorAll<HTMLInputElement>('[data-i18n-placeholder]').forEach((element) => {
    const key = getTranslationKey(element, 'i18nPlaceholder');
    if (key) element.placeholder = translate(language, key);
  });

  if (languageSelect) languageSelect.value = language;

  widget?.setAttribute('language', language);
  widget?.setAttribute('title', translate(language, 'widget.title'));
  widget?.setAttribute('welcome', translate(language, 'widget.welcome'));
}

const initialLanguage = resolveLanguage(readStoredLanguage(), window.navigator.language);
applyLanguage(initialLanguage);

languageSelect?.addEventListener('change', () => {
  const language = resolveLanguage(languageSelect.value, initialLanguage);
  persistLanguage(language);
  applyLanguage(language);
});

const search = document.querySelector<HTMLInputElement>('#article-search');
const topics = Array.from(document.querySelectorAll<HTMLElement>('[data-search]'));
search?.addEventListener('input', () => {
  topics.forEach((topic) => {
    topic.hidden = !matchesSearch(topic.dataset.search, search.value);
  });
});

createIcons({
  icons: { ArrowRight, ChevronRight, Compass, ReceiptText, Search, UserRound, Users },
});
