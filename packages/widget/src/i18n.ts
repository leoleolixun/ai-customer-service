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
  authenticationError: 'Your support session expired. Reopen support to reconnect.',
  conversationClosedError: 'This conversation is already closed.',
  conversationUnavailableError: 'This conversation is no longer available.',
  conversationStateChangedError: 'The conversation changed state. Refresh and try again.',
  modelUnavailableError: 'AI support is temporarily unavailable. Contact an agent or try later.',
  requestInProgressError: 'That message is still being processed. Please wait before retrying.',
  rateLimitedError: 'Too many requests. Please wait a moment and try again.',
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
  authenticationError: '客服会话已过期，请重新打开客服后连接。',
  conversationClosedError: '当前会话已经结束。',
  conversationUnavailableError: '当前会话已不可用。',
  conversationStateChangedError: '会话状态已变化，请刷新后重试。',
  modelUnavailableError: 'AI 客服暂时不可用，请联系人工客服或稍后重试。',
  requestInProgressError: '该消息仍在处理中，请稍候再重试。',
  rateLimitedError: '请求过于频繁，请稍后再试。',
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
