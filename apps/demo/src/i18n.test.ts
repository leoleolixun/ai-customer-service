import { describe, expect, it } from 'vitest';

import {
  isTranslationKey,
  matchesSearch,
  normalizeLanguage,
  resolveLanguage,
  translate,
} from './i18n';

describe('language resolution', () => {
  it('normalizes supported browser language variants', () => {
    expect(normalizeLanguage('en-US')).toBe('en');
    expect(normalizeLanguage('zh-Hans-CN')).toBe('zh-CN');
    expect(normalizeLanguage('fr-FR')).toBeNull();
  });

  it('prefers a stored language and falls back to the browser language', () => {
    expect(resolveLanguage('en', 'zh-CN')).toBe('en');
    expect(resolveLanguage(null, 'zh-TW')).toBe('zh-CN');
    expect(resolveLanguage('unsupported', 'fr-FR')).toBe('en');
  });
});

describe('translation helpers', () => {
  it('returns the requested language from the typed dictionary', () => {
    expect(isTranslationKey('search.title')).toBe(true);
    expect(isTranslationKey('missing.key')).toBe(false);
    expect(translate('en', 'search.title')).toBe('How can we help?');
    expect(translate('zh-CN', 'search.title')).toBe('需要什么帮助？');
  });

  it('matches both English and Chinese terms in a bilingual index', () => {
    const index = 'account profile password security 账户 个人资料 密码 安全';

    expect(matchesSearch(index, 'PASSWORD')).toBe(true);
    expect(matchesSearch(index, '账户')).toBe(true);
    expect(matchesSearch(index, 'invoice')).toBe(false);
    expect(matchesSearch(index, '  ')).toBe(true);
  });
});
