import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';

import { en, type Messages, zhCN } from '@/i18n/messages';

export type Language = 'en' | 'zh-CN';
export type MessageValues = Record<string, string | number>;

export const LANGUAGE_STORAGE_KEY = 'ai-support.language';

interface I18nContextValue {
  language: Language;
  messages: Messages;
  setLanguage: (language: Language) => void;
  format: (template: string, values?: MessageValues) => string;
  labelValue: (value: string) => string;
}

const dictionaries: Record<Language, Messages> = { en, 'zh-CN': zhCN };
const I18nContext = createContext<I18nContextValue | null>(null);

export function resolveInitialLanguage(
  storedLanguage: string | null,
  browserLanguage: string,
): Language {
  if (storedLanguage === 'en' || storedLanguage === 'zh-CN') return storedLanguage;
  return browserLanguage.toLowerCase().startsWith('zh') ? 'zh-CN' : 'en';
}

export function formatMessage(template: string, values: MessageValues = {}): string {
  return template.replace(/\{([^{}]+)\}/g, (placeholder, key: string) => {
    const value = values[key];
    return value === undefined ? placeholder : String(value);
  });
}

export const I18nProvider: React.FC<React.PropsWithChildren> = ({ children }) => {
  const [language, setLanguageState] = useState<Language>(() => resolveInitialLanguage(
    localStorage.getItem(LANGUAGE_STORAGE_KEY),
    navigator.language,
  ));

  useEffect(() => {
    document.documentElement.lang = language;
    document.title = dictionaries[language].app.name;
  }, [language]);

  const setLanguage = useCallback((nextLanguage: Language) => {
    localStorage.setItem(LANGUAGE_STORAGE_KEY, nextLanguage);
    document.documentElement.lang = nextLanguage;
    setLanguageState(nextLanguage);
  }, []);

  const value = useMemo<I18nContextValue>(() => ({
    language,
    messages: dictionaries[language],
    setLanguage,
    format: formatMessage,
    labelValue: (rawValue: string) => (
      dictionaries[language].values as Record<string, string>
    )[rawValue] ?? rawValue,
  }), [language, setLanguage]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
};

export function useI18n(): I18nContextValue {
  const context = useContext(I18nContext);
  if (!context) throw new Error('useI18n must be used inside I18nProvider');
  return context;
}
