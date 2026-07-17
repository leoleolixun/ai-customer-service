import { Check, Headphones, Send, XCircle } from 'lucide-react';
import {
  Alert,
  Box,
  Button,
  Chip,
  Divider,
  List,
  ListItemButton,
  ListItemText,
  Paper,
  TextField,
  Typography,
} from '@mui/material';
import { useQuery, useQueryClient, useSuspenseQuery } from '@tanstack/react-query';
import React, { useCallback, useEffect, useRef, useState } from 'react';

import { api, errorMessage } from '@/api/client';
import type { Handoff, Message } from '@/api/types';
import { useAuth } from '@/auth/AuthProvider';
import PageHeader from '@/components/PageHeader';
import { useI18n } from '@/i18n/I18nProvider';

const AgentPage: React.FC = () => {
  const { format, labelValue, language, messages } = useI18n();
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const { data: handoffs } = useSuspenseQuery({
    queryKey: ['handoffs'],
    queryFn: () => api<Handoff[]>('/v1/admin/handoffs'),
    refetchInterval: 3000,
  });
  const active = handoffs.filter((item) => ['pending', 'accepted'].includes(item.status));
  const [selectedId, setSelectedId] = useState<string | null>(active[0]?.id ?? null);
  const selected = active.find((item) => item.id === selectedId) ?? null;
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const messagesRef = useRef<HTMLDivElement>(null);
  const { data: conversationMessages = [] } = useQuery({
    queryKey: ['handoff-messages', selectedId],
    queryFn: () => api<Message[]>(`/v1/admin/handoffs/${selectedId}/messages`),
    enabled: Boolean(selectedId),
    refetchInterval: selectedId ? 2500 : false,
  });

  useEffect(() => {
    if (!selected && active[0]) setSelectedId(active[0].id);
    if (!selected && active.length === 0 && selectedId) setSelectedId(null);
  }, [active, selected, selectedId]);
  useEffect(() => {
    const container = messagesRef.current;
    if (container) container.scrollTop = container.scrollHeight;
  }, [conversationMessages]);

  const mutate = useCallback(async (path: string, body?: object) => {
    setBusy(true);
    setError(null);
    try {
      await api(path, { method: 'POST', body: body ? JSON.stringify(body) : undefined });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['handoffs'] }),
        queryClient.invalidateQueries({ queryKey: ['handoff-messages', selectedId] }),
      ]);
    } catch (cause) {
      setError(errorMessage(cause, messages.common.requestFailed));
    } finally {
      setBusy(false);
    }
  }, [messages.common.requestFailed, queryClient, selectedId]);

  const send = useCallback(async () => {
    if (!selected || !draft.trim()) return;
    const content = draft.trim();
    setDraft('');
    await mutate(`/v1/admin/handoffs/${selected.id}/messages`, { content });
  }, [draft, mutate, selected]);

  const isOwner =
    selected?.status === 'accepted' && selected.assigned_staff_user_id === user?.id;
  return (
    <>
      <PageHeader title={messages.agent.title} description={messages.agent.description} />
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', lg: '300px minmax(0, 1fr)' }, height: { lg: 'calc(100vh - 150px)' }, minHeight: 580 }}>
        <Paper variant="outlined" sx={{ display: 'grid', gridTemplateRows: 'auto minmax(0,1fr)', overflow: 'hidden' }}>
          <Box sx={{ alignItems: 'center', display: 'flex', justifyContent: 'space-between', px: 2, py: 1.5 }}><Typography fontSize={13} fontWeight={700}>{messages.agent.activeQueue}</Typography><Chip size="small" label={active.length} /></Box>
          <Divider />
          <List disablePadding sx={{ overflowY: 'auto' }}>
            {active.map((handoff) => (
              <ListItemButton key={handoff.id} selected={handoff.id === selectedId} onClick={() => setSelectedId(handoff.id)} sx={{ alignItems: 'flex-start', py: 1.5 }}>
                <ListItemText primary={handoff.reason ? labelValue(handoff.reason) : messages.agent.supportRequested} secondary={`${labelValue(handoff.status)} · ${new Date(handoff.created_at).toLocaleTimeString(language)}`} primaryTypographyProps={{ fontSize: 13, fontWeight: 650, noWrap: true }} secondaryTypographyProps={{ fontSize: 11 }} />
              </ListItemButton>
            ))}
          </List>
        </Paper>

        <Paper variant="outlined" sx={{ display: 'grid', gridTemplateRows: 'auto minmax(0, 1fr) auto', minWidth: 0, overflow: 'hidden' }}>
          {selected ? (
            <>
              <Box sx={{ alignItems: { sm: 'center' }, display: 'flex', flexDirection: { xs: 'column', sm: 'row' }, gap: 1, justifyContent: 'space-between', p: 2 }}>
                <Box sx={{ minWidth: 0 }}>
                  <Typography fontWeight={700}>{format(messages.agent.conversation, { id: selected.conversation_id.slice(0, 8) })}</Typography>
                  <Typography color="text.secondary" fontSize={12}>{selected.reason ? labelValue(selected.reason) : messages.agent.supportRequested}</Typography>
                  {selected.summary && (
                    <Typography color="text.secondary" fontSize={12} mt={0.75} sx={{ whiteSpace: 'pre-wrap' }}>
                      {format(messages.agent.summary, { summary: selected.summary })}
                    </Typography>
                  )}
                </Box>
                <Box sx={{ display: 'flex', gap: 1 }}>
                  {selected.status === 'pending' && <Button variant="contained" startIcon={<Check size={16} />} disabled={busy} onClick={() => void mutate(`/v1/admin/handoffs/${selected.id}/accept`)}>{messages.agent.accept}</Button>}
                  {isOwner && <Button color="error" startIcon={<XCircle size={16} />} disabled={busy} onClick={() => void mutate(`/v1/admin/handoffs/${selected.id}/close`, { reason: 'resolved' })}>{messages.agent.close}</Button>}
                </Box>
              </Box>
              <Divider />
              <Box ref={messagesRef} sx={{ bgcolor: '#f4f6f5', display: 'flex', flexDirection: 'column', gap: 1.5, overflowY: 'auto', p: 2 }}>
                {conversationMessages.map((message) => (
                  <Box key={message.id} sx={{ alignSelf: message.sender === 'user' ? 'flex-end' : 'flex-start', maxWidth: '78%' }}>
                    <Typography color="text.secondary" fontSize={10} sx={{ mb: 0.25, textAlign: message.sender === 'user' ? 'right' : 'left' }}>{message.sender === 'user' ? messages.agent.customer : message.sender === 'agent' ? messages.agent.agent : messages.agent.ai}</Typography>
                    <Box sx={{ bgcolor: message.sender === 'user' ? 'primary.main' : '#fff', border: 1, borderColor: message.sender === 'user' ? 'primary.main' : 'divider', borderRadius: 1, color: message.sender === 'user' ? '#fff' : 'text.primary', overflowWrap: 'anywhere', px: 1.5, py: 1 }}>{message.content}</Box>
                  </Box>
                ))}
              </Box>
              <Box sx={{ borderTop: 1, borderColor: 'divider', display: 'grid', gap: 1, gridTemplateColumns: 'minmax(0, 1fr) 42px', p: 1.5 }}>
                <TextField size="small" value={draft} onChange={(event) => setDraft(event.target.value)} placeholder={isOwner ? messages.agent.replyPlaceholder : messages.agent.acceptToReply} disabled={!isOwner} onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); void send(); } }} />
                <Button variant="contained" aria-label={messages.agent.sendReply} sx={{ minWidth: 42, p: 0 }} disabled={!isOwner || !draft.trim() || busy} onClick={() => void send()}><Send size={17} /></Button>
              </Box>
            </>
          ) : (
            <Box sx={{ alignItems: 'center', color: 'text.secondary', display: 'flex', flexDirection: 'column', gap: 1, justifyContent: 'center', p: 4 }}><Headphones size={28} /><Typography>{messages.agent.noActiveHandoffs}</Typography></Box>
          )}
        </Paper>
      </Box>
    </>
  );
};

export default AgentPage;
