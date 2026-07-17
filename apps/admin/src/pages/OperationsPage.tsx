import { Activity, Clock3, Coins, MessageSquareText } from 'lucide-react';
import {
  Box,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material';
import { useSuspenseQuery } from '@tanstack/react-query';
import React from 'react';

import { api } from '@/api/client';
import type { AuditLog, ConversationFeedback, ModelCall, UsageSummary } from '@/api/types';
import PageHeader from '@/components/PageHeader';
import { useI18n } from '@/i18n/I18nProvider';

const OperationsPage: React.FC = () => {
  const { format, labelValue, language, messages } = useI18n();
  const errorLabel = (code: string): string => (
    (messages.errors as Readonly<Record<string, string>>)[code] ?? messages.operations.unknownError
  );
  const { data: usage } = useSuspenseQuery({
    queryKey: ['usage-summary'],
    queryFn: () => api<UsageSummary>('/v1/admin/usage/summary'),
  });
  const { data: logs } = useSuspenseQuery({
    queryKey: ['audit-logs'],
    queryFn: () => api<AuditLog[]>('/v1/admin/audit-logs?limit=100'),
  });
  const { data: modelCalls } = useSuspenseQuery({
    queryKey: ['model-calls'],
    queryFn: () => api<ModelCall[]>('/v1/admin/usage/model-calls?limit=100'),
  });
  const { data: feedback } = useSuspenseQuery({
    queryKey: ['conversation-feedback'],
    queryFn: () => api<ConversationFeedback[]>('/v1/admin/feedback?limit=100'),
  });
  const metrics = [
    { label: messages.operations.requests, value: usage.total_requests.toLocaleString(language), icon: Activity },
    { label: messages.operations.tokens, value: (usage.prompt_tokens + usage.completion_tokens).toLocaleString(language), icon: MessageSquareText },
    { label: messages.operations.averageLatency, value: format(messages.operations.milliseconds, { value: Math.round(usage.average_duration_ms).toLocaleString(language) }), icon: Clock3 },
    { label: messages.operations.estimatedCost, value: `$${(usage.estimated_cost_micros / 1_000_000).toFixed(4)}`, icon: Coins },
  ];
  return (
    <>
      <PageHeader title={messages.operations.title} description={messages.operations.description} />
      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, 1fr)', xl: 'repeat(4, 1fr)' }, mb: 4 }}>
        {metrics.map((metric) => <Paper key={metric.label} variant="outlined" sx={{ alignItems: 'center', display: 'flex', gap: 1.5, p: 2.5 }}><Box sx={{ alignItems: 'center', bgcolor: 'primary.light', borderRadius: 1, color: 'primary.dark', display: 'flex', height: 40, justifyContent: 'center', width: 40 }}><metric.icon size={19} /></Box><Box><Typography color="text.secondary" fontSize={12}>{metric.label}</Typography><Typography fontSize={21} fontWeight={750}>{metric.value}</Typography></Box></Paper>)}
      </Box>
      <Typography component="h2" variant="h2" sx={{ mb: 1.5 }}>{messages.operations.conversationFeedback}</Typography>
      <TableContainer component={Paper} variant="outlined" sx={{ mb: 4 }}>
        <Table size="small">
          <TableHead><TableRow><TableCell>{messages.operations.time}</TableCell><TableCell>{messages.operations.rating}</TableCell><TableCell>{messages.operations.reply}</TableCell><TableCell>{messages.operations.comment}</TableCell></TableRow></TableHead>
          <TableBody>
            {feedback.map((item) => (
              <TableRow key={item.id} hover>
                <TableCell>{new Date(item.created_at).toLocaleString(language)}</TableCell>
                <TableCell><Typography color={item.rating === 'unhelpful' ? 'error.main' : 'success.main'} fontWeight={700}>{labelValue(item.rating)}</Typography></TableCell>
                <TableCell sx={{ maxWidth: 520 }}>{item.message_excerpt}</TableCell>
                <TableCell>{item.comment ?? '—'}</TableCell>
              </TableRow>
            ))}
            {feedback.length === 0 && <TableRow><TableCell colSpan={4}>{messages.operations.noFeedback}</TableCell></TableRow>}
          </TableBody>
        </Table>
      </TableContainer>
      <Typography component="h2" variant="h2" sx={{ mb: 1.5 }}>{messages.operations.recentModelCalls}</Typography>
      <TableContainer component={Paper} variant="outlined" sx={{ mb: 4 }}>
        <Table size="small">
          <TableHead><TableRow><TableCell>{messages.operations.time}</TableCell><TableCell>{messages.operations.model}</TableCell><TableCell>{messages.common.status}</TableCell><TableCell>{messages.operations.tokens}</TableCell><TableCell>{messages.operations.latency}</TableCell><TableCell>{messages.operations.cost}</TableCell></TableRow></TableHead>
          <TableBody>
            {modelCalls.map((call) => <TableRow key={call.id} hover><TableCell>{new Date(call.created_at).toLocaleString(language)}</TableCell><TableCell>{call.model_name}</TableCell><TableCell><Typography color={call.status === 'failed' ? 'error.main' : 'success.main'} fontWeight={700}>{labelValue(call.status)}</Typography>{call.error_code && <Typography color="text.secondary" fontSize={11} title={call.error_code}>{errorLabel(call.error_code)}</Typography>}</TableCell><TableCell>{(call.prompt_tokens + call.completion_tokens).toLocaleString(language)}</TableCell><TableCell>{format(messages.operations.milliseconds, { value: call.duration_ms.toLocaleString(language) })}</TableCell><TableCell>${(call.estimated_cost_micros / 1_000_000).toFixed(6)}</TableCell></TableRow>)}
            {modelCalls.length === 0 && <TableRow><TableCell colSpan={6}>{messages.operations.noModelCalls}</TableCell></TableRow>}
          </TableBody>
        </Table>
      </TableContainer>
      <Typography component="h2" variant="h2" sx={{ mb: 1.5 }}>{messages.operations.auditLog}</Typography>
      <TableContainer component={Paper} variant="outlined">
        <Table size="small"><TableHead><TableRow><TableCell>{messages.operations.time}</TableCell><TableCell>{messages.common.action}</TableCell><TableCell>{messages.operations.actor}</TableCell><TableCell>{messages.operations.resource}</TableCell><TableCell>{messages.operations.requestId}</TableCell></TableRow></TableHead><TableBody>{logs.map((log) => <TableRow key={log.id} hover><TableCell>{new Date(log.created_at).toLocaleString(language)}</TableCell><TableCell><Typography fontWeight={650} fontSize={12} title={log.action}>{labelValue(log.action)}</Typography></TableCell><TableCell><span title={log.actor_type}>{labelValue(log.actor_type)}</span> · {log.actor_id.slice(0, 12)}</TableCell><TableCell><span title={log.resource_type}>{labelValue(log.resource_type)}</span>{log.resource_id ? ` · ${log.resource_id.slice(0, 12)}` : ''}</TableCell><TableCell><Typography component="code" fontSize={11}>{log.request_id?.slice(0, 12) ?? '—'}</Typography></TableCell></TableRow>)}</TableBody></Table>
      </TableContainer>
    </>
  );
};

export default OperationsPage;
