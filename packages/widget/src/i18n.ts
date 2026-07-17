export const WIDGET_LANGUAGE_STORAGE_KEY = 'ai-support.language';

export const WIDGET_LANGUAGES = ['en', 'zh-CN'] as const;

export type WidgetLanguage = (typeof WIDGET_LANGUAGES)[number];

const english = {
  aiSupport: 'AI support',
  agentJoined: 'An agent has joined',
  agentOnline: 'Agent online',
  closeSupport: 'Close support',
  connecting: 'Connecting to support…',
  contactAgent: 'Contact an agent',
  conversationClosed: 'Conversation closed',
  defaultTitle: 'Support',
  defaultWelcome: 'How can we help today?',
  fallbackError: 'Support is temporarily unavailable. Please try again later.',
  feedbackSaved: 'Feedback saved',
  languageSelector: 'Language',
  markHelpful: 'Mark reply as helpful',
  markUnhelpful: 'Mark reply as unhelpful',
  message: 'Message',
  messagePlaceholder: 'Write a message',
  openSupport: 'Open support',
  rateReply: 'Rate this reply',
  senderAgent: 'Support agent',
  senderAI: 'AI support',
  senderSystem: 'System',
  senderUser: 'You',
  sendMessage: 'Send message',
  sources: 'Sources',
  waitingAgent: 'Waiting for an agent',
} as const;

export type WidgetTranslations = {
  readonly [Key in keyof typeof english]: string;
};

const simplifiedChinese = {
  aiSupport: 'AI 客服',
  agentJoined: '人工客服已加入',
  agentOnline: '人工客服在线',
  closeSupport: '关闭客服',
  connecting: '正在连接客服…',
  contactAgent: '联系人工客服',
  conversationClosed: '会话已结束',
  defaultTitle: '在线客服',
  defaultWelcome: '您好，请问有什么可以帮您？',
  fallbackError: '客服暂时不可用，请稍后重试。',
  feedbackSaved: '反馈已保存',
  languageSelector: '语言',
  markHelpful: '标记回复有帮助',
  markUnhelpful: '标记回复没有帮助',
  message: '消息',
  messagePlaceholder: '请输入消息',
  openSupport: '打开客服',
  rateReply: '评价此回复',
  senderAgent: '人工客服',
  senderAI: 'AI 客服',
  senderSystem: '系统',
  senderUser: '你',
  sendMessage: '发送消息',
  sources: '参考来源',
  waitingAgent: '正在等待人工客服',
} satisfies WidgetTranslations;

const dictionaries: Record<WidgetLanguage, WidgetTranslations> = {
  en: english,
  'zh-CN': simplifiedChinese,
};

export function parseWidgetLanguage(value: string | null | undefined): WidgetLanguage | undefined {
  return WIDGET_LANGUAGES.find((language) => language === value);
}

export function resolveWidgetLanguage(preferred?: string | null): WidgetLanguage {
  const explicit = parseWidgetLanguage(preferred);
  if (explicit) return explicit;

  try {
    const stored = parseWidgetLanguage(globalThis.localStorage?.getItem(WIDGET_LANGUAGE_STORAGE_KEY));
    if (stored) return stored;
  } catch {
    // Storage can be unavailable in privacy-restricted embedding contexts.
  }

  const browserLanguage = globalThis.navigator?.language?.toLowerCase() ?? '';
  return browserLanguage.startsWith('zh') ? 'zh-CN' : 'en';
}

export function persistWidgetLanguage(language: WidgetLanguage): void {
  try {
    globalThis.localStorage?.setItem(WIDGET_LANGUAGE_STORAGE_KEY, language);
  } catch {
    // The active Widget still switches language when storage is unavailable.
  }
}

export function getWidgetTranslations(language: WidgetLanguage): WidgetTranslations {
  return dictionaries[language];
}
