import '@testing-library/jest-dom/vitest';

import { act, cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import './index';
import Widget from './Widget';
import { AISupportWidgetElement } from './index';
import { WIDGET_LANGUAGE_STORAGE_KEY } from './i18n';

const conversation = {
  id: 'conversation-1',
  application_id: 'application-1',
  mode: 'ai',
  status: 'open',
  created_at: '2026-07-17T00:00:00Z',
  updated_at: '2026-07-17T00:00:00Z',
};

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function successfulFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const url = String(input);
  if (url.endsWith('/v1/chat/sessions') && init?.method === 'POST') {
    return Promise.resolve(json(conversation, 201));
  }
  if (url.endsWith('/messages')) return Promise.resolve(json([]));
  if (url.endsWith('/handoff')) {
    return Promise.resolve(json({ code: 'handoff_not_found', detail: 'Not found' }, 404));
  }
  return Promise.resolve(json(conversation));
}

describe('Widget', () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    vi.stubGlobal('fetch', vi.fn(successfulFetch));
  });

  afterEach(() => {
    cleanup();
    document.body.replaceChildren();
    vi.unstubAllGlobals();
  });

  it('mounts behind an accessible launcher and initializes when opened', async () => {
    const user = userEvent.setup();
    render(
      <Widget
        applicationId="application-1"
        baseUrl="https://support.example.test"
        getToken={() => 'customer-token'}
        sessionKey="customer-1"
        title="Example support"
        welcome="How can we help?"
      />,
    );

    await user.click(screen.getByRole('button', { name: 'Open support' }));

    const dialog = await screen.findByRole('dialog', { name: 'Example support' });
    expect(dialog).toHaveAttribute('aria-modal', 'false');
    expect(await screen.findByText('How can we help?')).toBeVisible();
    expect(screen.getByRole('textbox', { name: 'Message' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Send message' })).toBeDisabled();
    expect(sessionStorage.getItem(
      'ai-support:https://support.example.test:application-1:customer-1:conversation',
    )).toBe('conversation-1');
  });

  it('announces a Problem Details error and keeps the close action available', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(json({ code: 'provider_unavailable', detail: 'Gateway unavailable' }, 503))),
    );
    const user = userEvent.setup();
    render(
      <Widget
        applicationId="application-1"
        baseUrl="https://support.example.test"
        getToken={() => 'customer-token'}
        title="Example support"
        welcome="How can we help?"
      />,
    );

    await user.click(screen.getByRole('button', { name: 'Open support' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Gateway unavailable');
    await user.click(screen.getByRole('button', { name: 'Close support' }));
    expect(screen.getByRole('button', { name: 'Open support' })).toBeVisible();
  });

  it('renders the default interface and fallback error in Simplified Chinese', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('network unavailable'))));
    const user = userEvent.setup();
    render(
      <Widget
        applicationId="application-1"
        baseUrl="https://support.example.test"
        getToken={() => 'customer-token'}
        language="zh-CN"
      />,
    );

    await user.click(screen.getByRole('button', { name: '打开客服' }));

    expect(await screen.findByRole('dialog', { name: '在线客服' })).toBeVisible();
    expect(await screen.findByText('您好，请问有什么可以帮您？')).toBeVisible();
    expect(screen.getByRole('combobox', { name: '语言' })).toHaveValue('zh-CN');
    expect(screen.getByRole('textbox', { name: '消息' })).toHaveAttribute('placeholder', '请输入消息');
    expect(screen.getByRole('button', { name: '发送消息' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '联系人工客服' })).toBeEnabled();
    expect(screen.getByRole('button', { name: '关闭客服' })).toBeEnabled();
    expect(await screen.findByRole('alert')).toHaveTextContent('客服暂时不可用，请稍后重试。');
  });

  it('persists a user language choice and uses it when the host does not specify one', async () => {
    const user = userEvent.setup();
    const fetchMock = vi.mocked(globalThis.fetch);
    const view = render(
      <Widget
        applicationId="application-1"
        baseUrl="https://support.example.test"
        getToken={() => 'customer-token'}
        language="en"
        title="Acme support"
        welcome="Welcome to Acme"
      />,
    );

    await user.click(screen.getByRole('button', { name: 'Open support' }));
    await user.selectOptions(screen.getByRole('combobox', { name: 'Language' }), 'zh-CN');

    expect(localStorage.getItem(WIDGET_LANGUAGE_STORAGE_KEY)).toBe('zh-CN');
    expect(screen.getByRole('combobox', { name: '语言' })).toHaveValue('zh-CN');
    expect(screen.getByRole('dialog', { name: 'Acme support' })).toBeVisible();
    expect(screen.getByText('Welcome to Acme')).toBeVisible();
    expect(screen.getByRole('button', { name: '关闭客服' })).toBeEnabled();

    await user.type(screen.getByRole('textbox', { name: '消息' }), '请使用中文回答');
    await user.click(screen.getByRole('button', { name: '发送消息' }));
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        'https://support.example.test/v1/chat/sessions/conversation-1/messages',
        expect.objectContaining({
          body: JSON.stringify({ content: '请使用中文回答', locale: 'zh-CN' }),
          method: 'POST',
        }),
      );
    });

    view.unmount();
    render(
      <Widget
        applicationId="application-1"
        baseUrl="https://support.example.test"
        getToken={() => 'customer-token'}
      />,
    );

    expect(screen.getByRole('button', { name: '打开客服' })).toBeVisible();
  });

  it('uses the browser language when neither the host nor storage specifies one', () => {
    vi.spyOn(window.navigator, 'language', 'get').mockReturnValue('zh-TW');

    render(
      <Widget
        applicationId="application-1"
        baseUrl="https://support.example.test"
        getToken={() => 'customer-token'}
      />,
    );

    expect(screen.getByRole('button', { name: '打开客服' })).toBeVisible();
  });

  it('uses the language attribute and rerenders immediately when it changes', async () => {
    expect(AISupportWidgetElement.observedAttributes).toContain('language');
    const element = document.createElement('ai-support-widget') as AISupportWidgetElement;
    element.setAttribute('token', 'customer-token');
    element.setAttribute('language', 'zh-CN');

    act(() => document.body.append(element));
    const mount = element.shadowRoot?.querySelector('div') as HTMLElement;
    await waitFor(() => {
      expect(within(mount).getByRole('button', { name: '打开客服' })).toBeVisible();
    });

    act(() => element.setAttribute('language', 'en'));

    await waitFor(() => {
      expect(within(mount).getByRole('button', { name: 'Open support' })).toBeVisible();
    });
  });

  it('opens an authenticated uploaded citation when no external source URL exists', async () => {
    const citationMessage = {
      id: 'message-with-uploaded-source',
      conversation_id: conversation.id,
      sender: 'ai',
      content: 'The source contains the verified policy.',
      status: 'completed',
      error_code: null,
      citations: [
        {
          id: 'citation-uploaded-1',
          document_id: 'document-uploaded-1',
          chunk_id: 'chunk-uploaded-1',
          quote: 'Verified policy text',
          source_title: 'Uploaded policy',
          source_url: null,
          score: 0.9,
        },
      ],
      created_at: conversation.created_at,
      updated_at: conversation.updated_at,
    };
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith('/v1/chat/sessions') && init?.method === 'POST') {
        return Promise.resolve(json(conversation, 201));
      }
      if (url.endsWith('/messages')) return Promise.resolve(json([citationMessage]));
      if (url.endsWith('/handoff')) {
        return Promise.resolve(json({ code: 'handoff_not_found', detail: 'Not found' }, 404));
      }
      if (url.endsWith('/citations/citation-uploaded-1/source')) {
        return Promise.resolve(
          new Response('Verified policy text', {
            headers: { 'Content-Type': 'text/plain' },
          }),
        );
      }
      return Promise.resolve(json(conversation));
    });
    vi.stubGlobal('fetch', fetchMock);
    const objectUrl = vi.fn(() => 'blob:uploaded-policy');
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: objectUrl });
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: vi.fn() });
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
    const user = userEvent.setup();
    render(
      <Widget
        applicationId="application-1"
        baseUrl="https://support.example.test"
        getToken={() => 'customer-token'}
        title="Example support"
        welcome="How can we help?"
      />,
    );

    await user.click(screen.getByRole('button', { name: 'Open support' }));
    await user.click(await screen.findByRole('button', { name: 'Uploaded policy' }));

    await waitFor(() => expect(objectUrl).toHaveBeenCalledOnce());
    expect(click).toHaveBeenCalledOnce();
    expect(fetchMock).toHaveBeenCalledWith(
      'https://support.example.test/v1/chat/sessions/conversation-1/citations/citation-uploaded-1/source',
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: 'Bearer customer-token' }),
      }),
    );
  });

  it('refreshes messages while a human handoff is active', async () => {
    let requested = false;
    const agentMessage = {
      id: 'agent-message-1',
      conversation_id: conversation.id,
      sender: 'agent',
      content: 'A human agent reply',
      status: 'completed',
      error_code: null,
      citations: [],
      created_at: conversation.created_at,
      updated_at: conversation.updated_at,
    };
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith('/v1/chat/sessions') && init?.method === 'POST') {
        return Promise.resolve(json(conversation, 201));
      }
      if (url.endsWith('/handoff') && init?.method === 'POST') {
        requested = true;
        return Promise.resolve(json({
          id: 'handoff-1',
          conversation_id: conversation.id,
          status: 'pending',
        }, 201));
      }
      if (url.endsWith('/handoff')) {
        return requested
          ? Promise.resolve(json({
              id: 'handoff-1',
              conversation_id: conversation.id,
              status: 'accepted',
            }))
          : Promise.resolve(json({ code: 'handoff_not_found', detail: 'Not found' }, 404));
      }
      if (url.endsWith('/messages')) {
        return Promise.resolve(json(requested ? [agentMessage] : []));
      }
      return Promise.resolve(json(conversation));
    });
    vi.stubGlobal('fetch', fetchMock);
    const user = userEvent.setup();
    render(
      <Widget
        applicationId="application-1"
        baseUrl="https://support.example.test"
        getToken={() => 'customer-token'}
        title="Example support"
        welcome="How can we help?"
      />,
    );

    await user.click(screen.getByRole('button', { name: 'Open support' }));
    await user.click(await screen.findByRole('button', { name: 'Contact an agent' }));

    expect(await screen.findByText('A human agent reply')).toBeVisible();
    expect(screen.getByText('Agent online')).toBeVisible();
    expect(fetchMock).toHaveBeenCalledWith(
      'https://support.example.test/v1/chat/sessions/conversation-1/handoff',
      expect.objectContaining({
        body: JSON.stringify({ reason: 'customer_requested_handoff' }),
        method: 'POST',
      }),
    );
  });

  it('can disconnect and reconnect the custom element without losing its mount point', async () => {
    const element = document.createElement('ai-support-widget') as AISupportWidgetElement;
    element.setAttribute('token', 'customer-token');
    element.setAttribute('title', 'Embedded support');

    act(() => document.body.append(element));
    await waitFor(() => {
      const mount = element.shadowRoot?.querySelector('div') as HTMLElement;
      expect(within(mount).getByRole('button', {
        name: 'Open support',
      })).toBeVisible();
    });

    act(() => element.remove());
    act(() => document.body.append(element));

    await waitFor(() => {
      expect(element.shadowRoot?.querySelectorAll('style')).toHaveLength(1);
      const mount = element.shadowRoot?.querySelector('div') as HTMLElement;
      expect(within(mount).getByRole('button', {
        name: 'Open support',
      })).toBeVisible();
    });
  });
});
