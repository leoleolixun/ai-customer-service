import '@testing-library/jest-dom/vitest';

import { cleanup, render, screen } from '@testing-library/react';
import React from 'react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import {
  formatMessage,
  I18nProvider,
  LANGUAGE_STORAGE_KEY,
  useI18n,
} from '@/i18n/I18nProvider';

const LanguageProbe: React.FC = () => {
  const { language, messages } = useI18n();
  return <div>{language} · {messages.app.name}</div>;
};

describe('I18nProvider', () => {
  const originalLanguage = navigator.language;

  beforeEach(() => {
    localStorage.clear();
    Object.defineProperty(navigator, 'language', { configurable: true, value: 'en-US' });
  });

  afterEach(() => {
    cleanup();
    localStorage.clear();
    Object.defineProperty(navigator, 'language', { configurable: true, value: originalLanguage });
  });

  it('prefers a persisted language over the browser language', () => {
    localStorage.setItem(LANGUAGE_STORAGE_KEY, 'zh-CN');

    render(<I18nProvider><LanguageProbe /></I18nProvider>);

    expect(screen.getByText('zh-CN · 客服管理后台')).toBeVisible();
    expect(document.documentElement.lang).toBe('zh-CN');
  });

  it('uses a Chinese browser locale when no preference is stored', () => {
    Object.defineProperty(navigator, 'language', { configurable: true, value: 'zh-Hans-CN' });

    render(<I18nProvider><LanguageProbe /></I18nProvider>);

    expect(screen.getByText('zh-CN · 客服管理后台')).toBeVisible();
  });

  it('formats named message values', () => {
    expect(formatMessage('Hello, {name}. You have {count} items.', { name: 'Leo', count: 2 }))
      .toBe('Hello, Leo. You have 2 items.');
  });
});
