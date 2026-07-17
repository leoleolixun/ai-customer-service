import '@testing-library/jest-dom/vitest';

import { cleanup, render, screen } from '@testing-library/react';
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import ConversationsPage from './ConversationsPage';
import { I18nProvider, LANGUAGE_STORAGE_KEY } from '@/i18n/I18nProvider';

const conversation = {
  id: 'conversation-12345678',
  application_id: 'application-1',
  end_user_id: 'user-1',
  external_user_id: 'customer-42',
  mode: 'ai' as const,
  status: 'open' as const,
  created_at: '2026-07-17T08:00:00Z',
  updated_at: '2026-07-17T08:05:00Z',
};

const mocks = vi.hoisted(() => ({
  fetchConversations: vi.fn(),
  fetchMessages: vi.fn(),
}));

vi.mock('@tanstack/react-query', () => ({
  useSuspenseQuery: () => ({
    data: [{
      id: 'application-1',
      tenant_id: 'tenant-1',
      name: 'Storefront',
      public_key: 'pk_test',
      allowed_origins: [],
      rate_limit_per_minute: 60,
      status: 'active',
      created_at: '2026-07-17T00:00:00Z',
      updated_at: '2026-07-17T00:00:00Z',
    }],
  }),
  useSuspenseInfiniteQuery: () => ({
    data: { pages: [{ items: [conversation], next_cursor: null, has_more: false }] },
    fetchNextPage: mocks.fetchConversations,
    hasNextPage: false,
    isFetchingNextPage: false,
  }),
  useInfiniteQuery: () => ({
    data: {
      pages: [{
        items: [{
          id: 'message-1',
          conversation_id: conversation.id,
          sender: 'ai',
          content: 'Returns are accepted within 30 days.',
          status: 'completed',
          error_code: null,
          citations: [{
            id: 'citation-1',
            source_title: 'Returns policy',
            source_url: 'https://docs.example.test/returns',
            quote: 'Return eligible items within 30 days.',
          }],
          model_info: {
            model: 'glm-4-flash',
            grounding: 'evidence',
            evidence_count: 1,
            prompt_tokens: 12,
            completion_tokens: 8,
          },
          created_at: '2026-07-17T08:05:00Z',
          updated_at: '2026-07-17T08:05:00Z',
        }, {
          id: 'message-2',
          conversation_id: conversation.id,
          sender: 'ai',
          content: '',
          status: 'failed',
          error_code: 'model_provider_failed',
          citations: [],
          model_info: {},
          created_at: '2026-07-17T08:06:00Z',
          updated_at: '2026-07-17T08:06:00Z',
        }],
        next_cursor: null,
        has_more: false,
      }],
    },
    error: null,
    fetchNextPage: mocks.fetchMessages,
    hasNextPage: false,
    isFetchingNextPage: false,
    isLoading: false,
  }),
}));

describe('ConversationsPage', () => {
  beforeEach(() => {
    localStorage.clear();
    mocks.fetchConversations.mockReset();
    mocks.fetchMessages.mockReset();
  });

  afterEach(cleanup);

  it('shows tenant conversations, citations, and model details in English', async () => {
    render(<I18nProvider><ConversationsPage /></I18nProvider>);

    expect(await screen.findByRole('heading', { name: 'Conversations' })).toBeVisible();
    expect(screen.getByText('customer-42')).toBeVisible();
    expect(screen.getByText('Returns are accepted within 30 days.')).toBeVisible();
    expect(screen.getByText('Returns policy')).toBeVisible();
    expect(screen.getByRole('link', { name: /Open source/ })).toHaveAttribute(
      'href',
      'https://docs.example.test/returns',
    );
    expect(screen.getByText(/glm-4-flash/)).toBeVisible();
    expect(screen.getByText('This AI reply could not be generated.')).toBeVisible();
    expect(screen.getByText('Reason: The model provider request failed.')).toBeVisible();
  });

  it('renders the conversation workflow in Simplified Chinese', async () => {
    localStorage.setItem(LANGUAGE_STORAGE_KEY, 'zh-CN');
    render(<I18nProvider><ConversationsPage /></I18nProvider>);

    expect(await screen.findByRole('heading', { name: '会话记录' })).toBeVisible();
    expect(screen.getByText('会话列表')).toBeVisible();
    expect(screen.getByText('引用来源')).toBeVisible();
    expect(screen.getByRole('link', { name: /打开来源/ })).toBeVisible();
    expect(screen.getByText('依据状态: 有知识依据')).toBeVisible();
    expect(screen.getByText(/输入 12 · 输出 8 Token/)).toBeVisible();
    expect(screen.getByText('这条 AI 回复生成失败。')).toBeVisible();
    expect(screen.getByText('原因：模型 Provider 请求失败。')).toBeVisible();
  });
});
