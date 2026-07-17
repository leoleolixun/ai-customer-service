import '@testing-library/jest-dom/vitest';

import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  formatMessage,
  I18nProvider,
  LANGUAGE_STORAGE_KEY,
  useI18n,
} from '@/i18n/I18nProvider';

const LanguageProbe: React.FC = () => {
  const { labelValue, language, messages } = useI18n();
  return (
    <div>
      {language} · {messages.app.name} · {labelValue('active')} ·{' '}
      {labelValue('customer_requested_handoff')}
    </div>
  );
};

const LanguageSetterProbe: React.FC = () => {
  const { language, setLanguage } = useI18n();
  return (
    <div>
      <span>{language}</span>
      <button type="button" onClick={() => setLanguage('zh-CN')}>switch</button>
    </div>
  );
};

describe('I18nProvider', () => {
  const originalLanguage = navigator.language;

  beforeEach(() => {
    localStorage.clear();
    Object.defineProperty(navigator, 'language', { configurable: true, value: 'en-US' });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    localStorage.clear();
    Object.defineProperty(navigator, 'language', { configurable: true, value: originalLanguage });
  });

  it('prefers a persisted language over the browser language', () => {
    localStorage.setItem(LANGUAGE_STORAGE_KEY, 'zh-CN');

    render(<I18nProvider><LanguageProbe /></I18nProvider>);

    expect(screen.getByText('zh-CN · 客服管理后台 · 启用 · 客户申请人工客服')).toBeVisible();
    expect(document.documentElement.lang).toBe('zh-CN');
  });

  it('uses a Chinese browser locale when no preference is stored', () => {
    Object.defineProperty(navigator, 'language', { configurable: true, value: 'zh-Hans-CN' });

    render(<I18nProvider><LanguageProbe /></I18nProvider>);

    expect(screen.getByText('zh-CN · 客服管理后台 · 启用 · 客户申请人工客服')).toBeVisible();
  });

  it('formats named message values', () => {
    expect(formatMessage('Hello, {name}. You have {count} items.', { name: 'Leo', count: 2 }))
      .toBe('Hello, Leo. You have 2 items.');
  });

  it('falls back to the browser language when storage reads fail', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new DOMException('Storage is disabled');
    });
    Object.defineProperty(navigator, 'language', { configurable: true, value: 'zh-CN' });

    render(<I18nProvider><LanguageProbe /></I18nProvider>);

    expect(screen.getByText('zh-CN · 客服管理后台 · 启用 · 客户申请人工客服')).toBeVisible();
  });

  it('switches the active page when storage writes fail', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('Storage is disabled');
    });
    render(<I18nProvider><LanguageSetterProbe /></I18nProvider>);

    fireEvent.click(screen.getByRole('button', { name: 'switch' }));

    expect(screen.getByText('zh-CN')).toBeVisible();
    expect(document.documentElement.lang).toBe('zh-CN');
  });
});
