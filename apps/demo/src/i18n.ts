export const SUPPORTED_LANGUAGES = ['en', 'zh-CN'] as const;

export type SupportedLanguage = (typeof SUPPORTED_LANGUAGES)[number];

export const LANGUAGE_STORAGE_KEY = 'ai-support.language';

const english = {
  'page.title': 'Northstar Help Center',
  'brand.homeLabel': 'Northstar Help Center home',
  'brand.helpCenter': 'Help Center',
  'navigation.label': 'Help center navigation',
  'navigation.guides': 'Guides',
  'navigation.status': 'Service status',
  'language.label': 'Language',
  'language.english': 'English',
  'language.chinese': 'Simplified Chinese',
  'search.eyebrow': 'Northstar Support',
  'search.title': 'How can we help?',
  'search.label': 'Search help articles',
  'search.placeholder': 'Search help articles',
  'topics.label': 'Help topics',
  'topics.account.title': 'Account',
  'topics.account.description': 'Profile settings, password recovery, and account security.',
  'topics.billing.title': 'Billing',
  'topics.billing.description': 'Plans, invoices, payment methods, and billing contacts.',
  'topics.workspace.title': 'Workspace',
  'topics.workspace.description': 'Invite teammates, assign roles, and manage your workspace.',
  'topics.viewArticles': 'View articles',
  'articles.eyebrow': 'Popular articles',
  'articles.title': 'Common questions',
  'articles.resetPassword': 'Reset a forgotten password',
  'articles.downloadInvoice': 'Download a monthly invoice',
  'articles.inviteMember': 'Invite a workspace member',
  'articles.changeSubscription': 'Cancel or change a subscription',
  'status.operational': 'All systems operational',
  'footer.copyright': '© 2026 Northstar',
  'widget.title': 'Northstar Support',
  'widget.welcome': 'Ask a question about your Northstar account.',
} as const;

export type TranslationKey = keyof typeof english;

export function isTranslationKey(key: string): key is TranslationKey {
  return Object.prototype.hasOwnProperty.call(english, key);
}

const simplifiedChinese: Record<TranslationKey, string> = {
  'page.title': 'Northstar 帮助中心',
  'brand.homeLabel': 'Northstar 帮助中心首页',
  'brand.helpCenter': '帮助中心',
  'navigation.label': '帮助中心导航',
  'navigation.guides': '使用指南',
  'navigation.status': '服务状态',
  'language.label': '语言',
  'language.english': '英语',
  'language.chinese': '简体中文',
  'search.eyebrow': 'Northstar 客户支持',
  'search.title': '需要什么帮助？',
  'search.label': '搜索帮助文章',
  'search.placeholder': '搜索帮助文章',
  'topics.label': '帮助主题',
  'topics.account.title': '账户',
  'topics.account.description': '个人资料设置、密码找回和账户安全。',
  'topics.billing.title': '账单',
  'topics.billing.description': '套餐、发票、支付方式和账单联系人。',
  'topics.workspace.title': '工作区',
  'topics.workspace.description': '邀请团队成员、分配角色并管理工作区。',
  'topics.viewArticles': '查看文章',
  'articles.eyebrow': '热门文章',
  'articles.title': '常见问题',
  'articles.resetPassword': '重置忘记的密码',
  'articles.downloadInvoice': '下载月度发票',
  'articles.inviteMember': '邀请工作区成员',
  'articles.changeSubscription': '取消或更改订阅',
  'status.operational': '所有系统运行正常',
  'footer.copyright': '© 2026 Northstar',
  'widget.title': 'Northstar 客户支持',
  'widget.welcome': '欢迎咨询 Northstar 账户相关问题。',
};

const translations: Record<SupportedLanguage, Record<TranslationKey, string>> = {
  en: english,
  'zh-CN': simplifiedChinese,
};

export function normalizeLanguage(language: string | null | undefined): SupportedLanguage | null {
  if (!language) return null;

  const normalized = language.trim().toLowerCase();
  if (normalized === 'en' || normalized.startsWith('en-')) return 'en';
  if (normalized === 'zh' || normalized.startsWith('zh-')) return 'zh-CN';
  return null;
}

export function resolveLanguage(
  storedLanguage: string | null | undefined,
  browserLanguage: string | null | undefined,
): SupportedLanguage {
  return normalizeLanguage(storedLanguage) ?? normalizeLanguage(browserLanguage) ?? 'en';
}

export function translate(language: SupportedLanguage, key: TranslationKey): string {
  return translations[language][key];
}

export function matchesSearch(searchIndex: string | undefined, query: string): boolean {
  const normalizedQuery = query.trim().toLocaleLowerCase();
  if (!normalizedQuery) return true;
  return (searchIndex ?? '').toLocaleLowerCase().includes(normalizedQuery);
}
