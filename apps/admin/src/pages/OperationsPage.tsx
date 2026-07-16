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

const OperationsPage: React.FC = () => {
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
    { label: 'Requests', value: usage.total_requests.toLocaleString(), icon: Activity },
    { label: 'Tokens', value: (usage.prompt_tokens + usage.completion_tokens).toLocaleString(), icon: MessageSquareText },
    { label: 'Average latency', value: `${Math.round(usage.average_duration_ms)} ms`, icon: Clock3 },
    { label: 'Estimated cost', value: `$${(usage.estimated_cost_micros / 1_000_000).toFixed(4)}`, icon: Coins },
  ];
  return (
    <>
      <PageHeader title="Operations" description="AI usage and tenant audit activity for the last 30 days." />
      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, 1fr)', xl: 'repeat(4, 1fr)' }, mb: 4 }}>
        {metrics.map((metric) => <Paper key={metric.label} variant="outlined" sx={{ alignItems: 'center', display: 'flex', gap: 1.5, p: 2.5 }}><Box sx={{ alignItems: 'center', bgcolor: 'primary.light', borderRadius: 1, color: 'primary.dark', display: 'flex', height: 40, justifyContent: 'center', width: 40 }}><metric.icon size={19} /></Box><Box><Typography color="text.secondary" fontSize={12}>{metric.label}</Typography><Typography fontSize={21} fontWeight={750}>{metric.value}</Typography></Box></Paper>)}
      </Box>
      <Typography component="h2" variant="h2" sx={{ mb: 1.5 }}>Conversation feedback</Typography>
      <TableContainer component={Paper} variant="outlined" sx={{ mb: 4 }}>
        <Table size="small">
          <TableHead><TableRow><TableCell>Time</TableCell><TableCell>Rating</TableCell><TableCell>Reply</TableCell><TableCell>Comment</TableCell></TableRow></TableHead>
          <TableBody>
            {feedback.map((item) => (
              <TableRow key={item.id} hover>
                <TableCell>{new Date(item.created_at).toLocaleString()}</TableCell>
                <TableCell><Typography color={item.rating === 'unhelpful' ? 'error.main' : 'success.main'} fontWeight={700}>{item.rating}</Typography></TableCell>
                <TableCell sx={{ maxWidth: 520 }}>{item.message_excerpt}</TableCell>
                <TableCell>{item.comment ?? '—'}</TableCell>
              </TableRow>
            ))}
            {feedback.length === 0 && <TableRow><TableCell colSpan={4}>No feedback submitted yet.</TableCell></TableRow>}
          </TableBody>
        </Table>
      </TableContainer>
      <Typography component="h2" variant="h2" sx={{ mb: 1.5 }}>Recent model calls</Typography>
      <TableContainer component={Paper} variant="outlined" sx={{ mb: 4 }}>
        <Table size="small">
          <TableHead><TableRow><TableCell>Time</TableCell><TableCell>Model</TableCell><TableCell>Status</TableCell><TableCell>Tokens</TableCell><TableCell>Latency</TableCell><TableCell>Cost</TableCell></TableRow></TableHead>
          <TableBody>
            {modelCalls.map((call) => <TableRow key={call.id} hover><TableCell>{new Date(call.created_at).toLocaleString()}</TableCell><TableCell>{call.model_name}</TableCell><TableCell><Typography color={call.status === 'failed' ? 'error.main' : 'success.main'} fontWeight={700}>{call.status}</Typography>{call.error_code && <Typography color="text.secondary" fontSize={11}>{call.error_code}</Typography>}</TableCell><TableCell>{(call.prompt_tokens + call.completion_tokens).toLocaleString()}</TableCell><TableCell>{call.duration_ms.toLocaleString()} ms</TableCell><TableCell>${(call.estimated_cost_micros / 1_000_000).toFixed(6)}</TableCell></TableRow>)}
            {modelCalls.length === 0 && <TableRow><TableCell colSpan={6}>No model calls in this period.</TableCell></TableRow>}
          </TableBody>
        </Table>
      </TableContainer>
      <Typography component="h2" variant="h2" sx={{ mb: 1.5 }}>Audit log</Typography>
      <TableContainer component={Paper} variant="outlined">
        <Table size="small"><TableHead><TableRow><TableCell>Time</TableCell><TableCell>Action</TableCell><TableCell>Actor</TableCell><TableCell>Resource</TableCell><TableCell>Request ID</TableCell></TableRow></TableHead><TableBody>{logs.map((log) => <TableRow key={log.id} hover><TableCell>{new Date(log.created_at).toLocaleString()}</TableCell><TableCell><Typography fontWeight={650} fontSize={12}>{log.action}</Typography></TableCell><TableCell>{log.actor_type} · {log.actor_id.slice(0, 12)}</TableCell><TableCell>{log.resource_type}{log.resource_id ? ` · ${log.resource_id.slice(0, 12)}` : ''}</TableCell><TableCell><Typography component="code" fontSize={11}>{log.request_id?.slice(0, 12) ?? '—'}</Typography></TableCell></TableRow>)}</TableBody></Table>
      </TableContainer>
    </>
  );
};

export default OperationsPage;
