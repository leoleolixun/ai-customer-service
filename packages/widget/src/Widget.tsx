import {
  Bot,
  ExternalLink,
  Headphones,
  MessageCircle,
  Send,
  ThumbsDown,
  ThumbsUp,
  UserRound,
  X,
} from 'lucide-react';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import {
  SupportApiError,
  SupportClient,
  type FeedbackRating,
  type Handoff,
  type Message,
} from '@ai-support/sdk';

interface WidgetProps {
  baseUrl: string;
  applicationId: string;
  getToken: () => string | Promise<string>;
  sessionKey?: string;
  title: string;
  welcome: string;
}

const Widget: React.FC<WidgetProps> = ({
  baseUrl,
  applicationId,
  getToken,
  sessionKey,
  title,
  welcome,
}) => {
  const [open, setOpen] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [handoff, setHandoff] = useState<Handoff | null>(null);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<Record<string, FeedbackRating>>({});
  const messagesRef = useRef<HTMLDivElement>(null);
  const client = useMemo(() => new SupportClient({ baseUrl, getToken }), [baseUrl, getToken]);
  const storageKey = sessionKey
    ? `ai-support:${baseUrl}:${applicationId}:${sessionKey}:conversation`
    : null;

  const initialize = useCallback(async () => {
    if (conversationId) return;
    setBusy(true);
    setError(null);
    try {
      let id = storageKey ? sessionStorage.getItem(storageKey) : null;
      if (id) {
        try {
          await client.getSession(id);
        } catch {
          id = null;
          if (storageKey) sessionStorage.removeItem(storageKey);
        }
      }
      if (!id) {
        const created = await client.createSession();
        id = created.id;
        if (storageKey) sessionStorage.setItem(storageKey, created.id);
      }
      const activeId = id;
      setConversationId(activeId);
      setMessages(await client.listMessages(activeId));
      try {
        setHandoff(await client.getHandoff(activeId));
      } catch (cause) {
        if (!(cause instanceof SupportApiError) || cause.status !== 404) throw cause;
      }
    } catch (cause) {
      setError(messageFromError(cause));
    } finally {
      setBusy(false);
    }
  }, [client, conversationId, storageKey]);

  useEffect(() => {
    if (open) void initialize();
  }, [initialize, open]);

  useEffect(() => {
    const container = messagesRef.current;
    if (container) container.scrollTop = container.scrollHeight;
  }, [messages]);

  useEffect(() => {
    if (
      !open ||
      !conversationId ||
      !handoff ||
      !['pending', 'accepted'].includes(handoff.status)
    ) return undefined;

    let active = true;
    let polling = false;
    const refreshHumanConversation = async (): Promise<void> => {
      if (polling) return;
      polling = true;
      try {
        const [currentHandoff, currentMessages] = await Promise.all([
          client.getHandoff(conversationId),
          client.listMessages(conversationId),
        ]);
        if (active) {
          setHandoff(currentHandoff);
          setMessages(currentMessages);
        }
      } catch {
        // Keep the current conversation visible and retry on the next poll.
      } finally {
        polling = false;
      }
    };
    void refreshHumanConversation();
    const timer = window.setInterval(() => void refreshHumanConversation(), 5_000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [client, conversationId, handoff?.status, open]);

  const send = useCallback(async () => {
    const content = draft.trim();
    if (!conversationId || !content || busy || handoff?.status === 'closed') return;
    setDraft('');
    setBusy(true);
    setError(null);
    const optimistic: Message = {
      id: `local-${crypto.randomUUID()}`,
      conversation_id: conversationId,
      sender: 'user',
      content,
      status: 'completed',
      error_code: null,
      citations: [],
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };
    setMessages((current) => [...current, optimistic]);
    try {
      if (handoff && ['pending', 'accepted'].includes(handoff.status)) {
        const saved = await client.sendHumanMessage(conversationId, content);
        setMessages((current) => current.map((item) => (item.id === optimistic.id ? saved : item)));
      } else {
        let assistantId = '';
        for await (const event of client.streamMessage(conversationId, content)) {
          if (event.type === 'message.started') {
            assistantId = event.data.message_id;
            setMessages((current) => [
              ...current,
              {
                id: assistantId,
                conversation_id: conversationId,
                sender: 'ai',
                content: '',
                status: 'generating',
                error_code: null,
                citations: [],
                created_at: new Date().toISOString(),
                updated_at: new Date().toISOString(),
              },
            ]);
          }
          if (event.type === 'message.delta') {
            setMessages((current) =>
              current.map((item) =>
                item.id === assistantId
                  ? { ...item, content: `${item.content}${event.data.delta}` }
                  : item,
              ),
            );
          }
          if (event.type === 'message.completed') {
            setMessages((current) =>
              current.map((item) => (item.id === assistantId ? event.data : item)),
            );
          }
          if (event.type === 'message.error') throw new Error(event.data.message);
        }
      }
    } catch (cause) {
      setError(messageFromError(cause));
      setMessages(await client.listMessages(conversationId).catch(() => []));
    } finally {
      setBusy(false);
    }
  }, [busy, client, conversationId, draft, handoff]);

  const requestHuman = useCallback(async () => {
    if (!conversationId || busy) return;
    setBusy(true);
    setError(null);
    try {
      setHandoff(await client.requestHandoff(conversationId, 'Customer requested human support'));
    } catch (cause) {
      setError(messageFromError(cause));
    } finally {
      setBusy(false);
    }
  }, [busy, client, conversationId]);

  const rateMessage = useCallback(async (messageId: string, rating: FeedbackRating) => {
    if (!conversationId) return;
    setError(null);
    try {
      await client.submitFeedback(conversationId, messageId, rating);
      setFeedback((current) => ({ ...current, [messageId]: rating }));
    } catch (cause) {
      setError(messageFromError(cause));
    }
  }, [client, conversationId]);

  const openCitationSource = useCallback(async (citationId: string) => {
    if (!conversationId) return;
    setError(null);
    try {
      const source = await client.getCitationSource(conversationId, citationId);
      const objectUrl = URL.createObjectURL(source);
      const link = document.createElement('a');
      link.href = objectUrl;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000);
    } catch (cause) {
      setError(messageFromError(cause));
    }
  }, [client, conversationId]);

  if (!open) {
    return (
      <button className="launcher" onClick={() => setOpen(true)} aria-label="Open support">
        <MessageCircle size={24} aria-hidden="true" />
      </button>
    );
  }

  return (
    <section className="panel" role="dialog" aria-label={title} aria-modal="false">
      <header className="header">
        <span className="brand-mark"><Bot size={22} aria-hidden="true" /></span>
        <span className="header-copy">
          <strong>{title}</strong>
          <span>{handoffLabel(handoff)}</span>
        </span>
        <button className="icon-button" onClick={() => setOpen(false)} aria-label="Close support">
          <X size={20} aria-hidden="true" />
        </button>
      </header>

      <div className="messages" aria-live="polite" ref={messagesRef}>
        {messages.length === 0 && (
          <div className="welcome">
            <MessageCircle size={28} aria-hidden="true" />
            {busy ? 'Connecting to support…' : welcome}
          </div>
        )}
        {messages.map((message) => (
          <article className={`message-row ${message.sender}`} key={message.id}>
            <span className="message-label">{senderLabel(message.sender)}</span>
            <div className="bubble">
              {message.content || '…'}
              {message.citations.length > 0 && (
                <div className="citations" aria-label="Sources">
                  {message.citations.map((citation) =>
                    citation.source_url ? (
                      <a
                        className="citation-link"
                        href={citation.source_url}
                        target="_blank"
                        rel="noreferrer"
                        key={citation.id}
                      >
                        <ExternalLink size={13} aria-hidden="true" />
                        {citation.source_title}
                      </a>
                    ) : (
                      <button
                        className="citation-link"
                        type="button"
                        key={citation.id}
                        onClick={() => void openCitationSource(citation.id)}
                      >
                        <ExternalLink size={13} aria-hidden="true" />
                        {citation.source_title}
                      </button>
                    ),
                  )}
                </div>
              )}
            </div>
            {['ai', 'agent'].includes(message.sender) && message.status === 'completed' && (
              <div className="feedback-actions" aria-label="Rate this reply">
                <button
                  className={feedback[message.id] === 'helpful' ? 'selected' : ''}
                  aria-label="Mark reply as helpful"
                  onClick={() => void rateMessage(message.id, 'helpful')}
                >
                  <ThumbsUp size={13} aria-hidden="true" />
                </button>
                <button
                  className={feedback[message.id] === 'unhelpful' ? 'selected' : ''}
                  aria-label="Mark reply as unhelpful"
                  onClick={() => void rateMessage(message.id, 'unhelpful')}
                >
                  <ThumbsDown size={13} aria-hidden="true" />
                </button>
                {feedback[message.id] && <span>Feedback saved</span>}
              </div>
            )}
          </article>
        ))}
      </div>

      <div>
        {handoff && ['pending', 'accepted'].includes(handoff.status) && (
          <div className="status-strip">
            <Headphones size={15} aria-hidden="true" />
            {handoff.status === 'pending' ? 'Waiting for an agent' : 'An agent has joined'}
          </div>
        )}
        <div className="composer">
          {error && <div className="error" role="alert">{error}</div>}
          <div className="composer-row">
            <textarea
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault();
                  void send();
                }
              }}
              placeholder="Write a message"
              rows={1}
              disabled={handoff?.status === 'closed'}
              aria-label="Message"
            />
            <button
              className="send-button"
              onClick={() => void send()}
              disabled={!draft.trim() || busy || handoff?.status === 'closed'}
              aria-label="Send message"
            >
              <Send size={18} aria-hidden="true" />
            </button>
          </div>
          {!handoff && (
            <button className="handoff-button" onClick={() => void requestHuman()} disabled={busy}>
              <UserRound size={14} aria-hidden="true" />
              Contact an agent
            </button>
          )}
        </div>
      </div>
    </section>
  );
};

function senderLabel(sender: Message['sender']): string {
  return { user: 'You', ai: 'AI support', agent: 'Support agent', system: 'System' }[sender];
}

function handoffLabel(handoff: Handoff | null): string {
  if (handoff?.status === 'pending') return 'Waiting for an agent';
  if (handoff?.status === 'accepted') return 'Agent online';
  if (handoff?.status === 'closed') return 'Conversation closed';
  return 'AI support';
}

function messageFromError(cause: unknown): string {
  if (cause instanceof SupportApiError) return cause.message;
  return 'Support is temporarily unavailable. Please try again later.';
}

export default Widget;
