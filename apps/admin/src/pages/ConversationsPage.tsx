import { ExternalLink, MessageSquareText, MessagesSquare } from 'lucide-react';
import {
  Alert,
  Box,
  Button,
  Chip,
  Divider,
  FormControl,
  InputLabel,
  LinearProgress,
  Link,
  List,
  ListItemButton,
  ListItemText,
  MenuItem,
  Paper,
  Select,
  Typography,
} from '@mui/material';
import {
  useInfiniteQuery,
  useSuspenseInfiniteQuery,
  useSuspenseQuery,
} from '@tanstack/react-query';
import React, { useEffect, useMemo, useState } from 'react';

import { api, errorMessage } from '@/api/client';
import type {
  AdminConversation,
  AdminConversationPage,
  AdminMessage,
  AdminMessagePage,
  Application,
} from '@/api/types';
import PageHeader from '@/components/PageHeader';
import { useI18n } from '@/i18n/I18nProvider';

type StatusFilter = '' | AdminConversation['status'];
type ModeFilter = '' | AdminConversation['mode'];

function buildConversationPath(
  applicationId: string,
  status: StatusFilter,
  mode: ModeFilter,
  before: string | null,
): string {
  const params = new URLSearchParams({ limit: '50' });
  if (applicationId) params.set('application_id', applicationId);
  if (status) params.set('status', status);
  if (mode) params.set('mode', mode);
  if (before) params.set('before', before);
  return `/v1/admin/conversations?${params.toString()}`;
}

function modelInfoNumber(message: AdminMessage, key: string): number | null {
  const value = message.model_info[key];
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function modelInfoString(message: AdminMessage, key: string): string | null {
  const value = message.model_info[key];
  return typeof value === 'string' && value ? value : null;
}

const ConversationsPage: React.FC = () => {
  const { format, labelValue, language, messages } = useI18n();
  const [applicationId, setApplicationId] = useState('');
  const [status, setStatus] = useState<StatusFilter>('');
  const [mode, setMode] = useState<ModeFilter>('');
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const { data: applications } = useSuspenseQuery({
    queryKey: ['applications'],
    queryFn: () => api<Application[]>('/v1/admin/applications'),
  });
  const applicationNames = useMemo(
    () => new Map(applications.map((application) => [application.id, application.name])),
    [applications],
  );
  const conversationsQuery = useSuspenseInfiniteQuery({
    queryKey: ['admin-conversations', applicationId, status, mode],
    queryFn: ({ pageParam }) => api<AdminConversationPage>(
      buildConversationPath(applicationId, status, mode, pageParam),
    ),
    initialPageParam: null as string | null,
    getNextPageParam: (page) => page.has_more ? page.next_cursor : undefined,
  });
  const conversations = conversationsQuery.data.pages.flatMap((page) => page.items);
  const selected = conversations.find((conversation) => conversation.id === selectedId) ?? null;

  useEffect(() => {
    if (!selected && conversations[0]) setSelectedId(conversations[0].id);
    if (!selected && conversations.length === 0) setSelectedId(null);
  }, [conversations, selected]);

  const messageQuery = useInfiniteQuery({
    queryKey: ['admin-conversation-messages', selectedId],
    queryFn: ({ pageParam }) => {
      const params = new URLSearchParams({ limit: '100' });
      if (pageParam) params.set('before', pageParam);
      return api<AdminMessagePage>(
        `/v1/admin/conversations/${selectedId}/messages?${params.toString()}`,
      );
    },
    initialPageParam: null as string | null,
    getNextPageParam: (page) => page.has_more ? page.next_cursor : undefined,
    enabled: selectedId !== null,
  });
  const conversationMessages = useMemo(
    () => [...(messageQuery.data?.pages ?? [])].reverse().flatMap((page) => page.items),
    [messageQuery.data?.pages],
  );

  return (
    <>
      <PageHeader title={messages.conversations.title} description={messages.conversations.description} />
      <Box sx={{ display: 'grid', gap: 1.5, gridTemplateColumns: { xs: '1fr', sm: 'repeat(3, minmax(0, 220px))' }, mb: 2 }}>
        <FormControl size="small">
          <InputLabel id="conversation-application-label">{messages.common.application}</InputLabel>
          <Select
            labelId="conversation-application-label"
            label={messages.common.application}
            value={applicationId}
            onChange={(event) => setApplicationId(event.target.value)}
          >
            <MenuItem value="">{messages.conversations.allApplications}</MenuItem>
            {applications.map((application) => (
              <MenuItem key={application.id} value={application.id}>{application.name}</MenuItem>
            ))}
          </Select>
        </FormControl>
        <FormControl size="small">
          <InputLabel id="conversation-status-label">{messages.conversations.statusFilter}</InputLabel>
          <Select
            labelId="conversation-status-label"
            label={messages.conversations.statusFilter}
            value={status}
            onChange={(event) => setStatus(event.target.value as StatusFilter)}
          >
            <MenuItem value="">{messages.conversations.allStatuses}</MenuItem>
            <MenuItem value="open">{labelValue('open')}</MenuItem>
            <MenuItem value="closed">{labelValue('closed')}</MenuItem>
          </Select>
        </FormControl>
        <FormControl size="small">
          <InputLabel id="conversation-mode-label">{messages.conversations.modeFilter}</InputLabel>
          <Select
            labelId="conversation-mode-label"
            label={messages.conversations.modeFilter}
            value={mode}
            onChange={(event) => setMode(event.target.value as ModeFilter)}
          >
            <MenuItem value="">{messages.conversations.allModes}</MenuItem>
            <MenuItem value="ai">{labelValue('ai')}</MenuItem>
            <MenuItem value="human">{labelValue('human')}</MenuItem>
          </Select>
        </FormControl>
      </Box>

      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', lg: '340px minmax(0, 1fr)' }, minHeight: { lg: 620 } }}>
        <Paper variant="outlined" sx={{ display: 'grid', gridTemplateRows: 'auto minmax(0, 1fr) auto', maxHeight: { xs: 420, lg: 'calc(100vh - 230px)' }, minHeight: 300, overflow: 'hidden' }}>
          <Box sx={{ alignItems: 'center', display: 'flex', justifyContent: 'space-between', px: 2, py: 1.5 }}>
            <Typography fontSize={13} fontWeight={700}>{messages.conversations.conversationList}</Typography>
            <Chip size="small" label={conversations.length} />
          </Box>
          <Divider />
          <List disablePadding sx={{ overflowY: 'auto' }}>
            {conversations.map((conversation) => (
              <ListItemButton
                key={conversation.id}
                selected={conversation.id === selectedId}
                onClick={() => setSelectedId(conversation.id)}
                sx={{ alignItems: 'flex-start', borderBottom: 1, borderColor: 'divider', py: 1.5 }}
              >
                <ListItemText
                  primary={conversation.external_user_id}
                  secondary={
                    <>
                      <Typography component="span" color="text.secondary" fontSize={11} display="block" noWrap>
                        {applicationNames.get(conversation.application_id) ?? conversation.application_id.slice(0, 8)}
                      </Typography>
                      <Typography component="span" color="text.secondary" fontSize={11}>
                        {labelValue(conversation.status)} · {labelValue(conversation.mode)} · {new Date(conversation.updated_at).toLocaleString(language)}
                      </Typography>
                    </>
                  }
                  primaryTypographyProps={{ fontSize: 13, fontWeight: 650, noWrap: true }}
                />
              </ListItemButton>
            ))}
            {conversations.length === 0 && (
              <Box sx={{ color: 'text.secondary', p: 3, textAlign: 'center' }}>
                <MessagesSquare size={25} />
                <Typography fontSize={13} mt={1}>{messages.conversations.noConversations}</Typography>
              </Box>
            )}
          </List>
          {conversationsQuery.hasNextPage && (
            <Button
              onClick={() => void conversationsQuery.fetchNextPage()}
              disabled={conversationsQuery.isFetchingNextPage}
              sx={{ borderRadius: 0 }}
            >
              {conversationsQuery.isFetchingNextPage
                ? messages.conversations.loadingOlder
                : messages.conversations.loadOlderConversations}
            </Button>
          )}
        </Paper>

        <Paper variant="outlined" sx={{ display: 'grid', gridTemplateRows: 'auto minmax(0, 1fr)', maxHeight: { lg: 'calc(100vh - 230px)' }, minHeight: 520, minWidth: 0, overflow: 'hidden' }}>
          {selected ? (
            <>
              <Box sx={{ p: 2 }}>
                <Box sx={{ alignItems: 'center', display: 'flex', flexWrap: 'wrap', gap: 1 }}>
                  <Typography fontWeight={700}>{format(messages.conversations.conversationLabel, { id: selected.id.slice(0, 8) })}</Typography>
                  <Chip size="small" label={labelValue(selected.status)} />
                  <Chip size="small" color={selected.mode === 'human' ? 'warning' : 'default'} label={labelValue(selected.mode)} />
                </Box>
                <Typography color="text.secondary" fontSize={12} mt={0.75}>
                  {messages.conversations.customer}: {selected.external_user_id} · {messages.conversations.application}: {applicationNames.get(selected.application_id) ?? selected.application_id}
                </Typography>
                <Typography color="text.secondary" fontSize={11} mt={0.25}>
                  {messages.conversations.createdAt}: {new Date(selected.created_at).toLocaleString(language)} · {messages.conversations.lastActivity}: {new Date(selected.updated_at).toLocaleString(language)}
                </Typography>
              </Box>
              <Divider />
              <Box sx={{ bgcolor: '#f4f6f5', display: 'flex', flexDirection: 'column', gap: 1.5, overflowY: 'auto', p: 2 }}>
                {messageQuery.isLoading && <LinearProgress aria-label={messages.app.loadingPage} />}
                {messageQuery.error && (
                  <Alert severity="error">{errorMessage(messageQuery.error, messages.common.requestFailed)}</Alert>
                )}
                {messageQuery.hasNextPage && (
                  <Button
                    size="small"
                    onClick={() => void messageQuery.fetchNextPage()}
                    disabled={messageQuery.isFetchingNextPage}
                  >
                    {messageQuery.isFetchingNextPage
                      ? messages.conversations.loadingOlder
                      : messages.conversations.loadOlderMessages}
                  </Button>
                )}
                {conversationMessages.map((message) => {
                  const model = modelInfoString(message, 'model');
                  const grounding = modelInfoString(message, 'grounding');
                  const evidenceCount = modelInfoNumber(message, 'evidence_count');
                  const promptTokens = modelInfoNumber(message, 'prompt_tokens');
                  const completionTokens = modelInfoNumber(message, 'completion_tokens');
                  const isCustomer = message.sender === 'user';
                  const failed = message.status === 'failed';
                  const failureReason = message.error_code
                    ? (messages.errors as Record<string, string>)[message.error_code]
                      ?? messages.conversations.unknownMessageError
                    : messages.conversations.unknownMessageError;
                  const content = message.content || (failed ? messages.conversations.failedMessage : '');
                  return (
                    <Box key={message.id} sx={{ alignSelf: isCustomer ? 'flex-end' : 'flex-start', maxWidth: { xs: '94%', md: '82%' }, minWidth: 0 }}>
                      <Typography color="text.secondary" fontSize={10} sx={{ mb: 0.25, textAlign: isCustomer ? 'right' : 'left' }}>
                        {labelValue(message.sender)} · {new Date(message.created_at).toLocaleString(language)}
                      </Typography>
                      <Box sx={{ bgcolor: isCustomer ? 'primary.main' : '#fff', border: 1, borderColor: isCustomer ? 'primary.main' : 'divider', borderRadius: 1, color: isCustomer ? '#fff' : 'text.primary', overflowWrap: 'anywhere', px: 1.5, py: 1 }}>
                        <Typography fontSize={14} sx={{ whiteSpace: 'pre-wrap' }}>{content}</Typography>
                      </Box>
                      {failed && (
                        <Typography color="error.main" fontSize={11} mt={0.5}>
                          {format(messages.conversations.failureReason, { reason: failureReason })}
                        </Typography>
                      )}
                      {message.citations.length > 0 && (
                        <Box sx={{ borderLeft: 2, borderColor: 'primary.light', mt: 0.75, pl: 1.25 }}>
                          <Typography color="text.secondary" fontSize={10} fontWeight={700}>{messages.conversations.citations}</Typography>
                          {message.citations.map((citation) => (
                            <Box key={citation.id} sx={{ mt: 0.75 }}>
                              <Typography fontSize={11} fontWeight={650}>{citation.source_title}</Typography>
                              <Typography color="text.secondary" fontSize={11}>{citation.quote}</Typography>
                              {citation.source_url && (
                                <Link href={citation.source_url} target="_blank" rel="noopener noreferrer" fontSize={11}>
                                  {messages.conversations.openSource} <ExternalLink size={10} />
                                </Link>
                              )}
                            </Box>
                          ))}
                        </Box>
                      )}
                      {(model || grounding || evidenceCount !== null) && (
                        <Box sx={{ color: 'text.secondary', display: 'flex', flexWrap: 'wrap', gap: 0.75, mt: 0.75 }}>
                          <Typography fontSize={10} fontWeight={700}>{messages.conversations.modelDetails}</Typography>
                          {model && <Typography fontSize={10}>{messages.conversations.model}: {model}</Typography>}
                          {grounding && <Typography fontSize={10}>{messages.conversations.grounding}: {labelValue(grounding)}</Typography>}
                          {evidenceCount !== null && <Typography fontSize={10}>{messages.conversations.evidenceCount}: {evidenceCount}</Typography>}
                          {promptTokens !== null && completionTokens !== null && (
                            <Typography fontSize={10}>{format(messages.conversations.tokenUsage, { prompt: promptTokens, completion: completionTokens })}</Typography>
                          )}
                        </Box>
                      )}
                    </Box>
                  );
                })}
                {!messageQuery.isLoading && !messageQuery.error && conversationMessages.length === 0 && (
                  <Box sx={{ alignItems: 'center', color: 'text.secondary', display: 'flex', flex: 1, flexDirection: 'column', justifyContent: 'center' }}>
                    <MessageSquareText size={26} />
                    <Typography fontSize={13} mt={1}>{messages.conversations.noMessages}</Typography>
                  </Box>
                )}
              </Box>
            </>
          ) : (
            <Box sx={{ alignItems: 'center', color: 'text.secondary', display: 'flex', flexDirection: 'column', gap: 1, justifyContent: 'center', p: 4 }}>
              <MessagesSquare size={30} />
              <Typography>{messages.conversations.selectConversation}</Typography>
            </Box>
          )}
        </Paper>
      </Box>
    </>
  );
};

export default ConversationsPage;
