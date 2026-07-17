import { Activity, AppWindow, CircleAlert, Headphones } from 'lucide-react';
import { Box, Paper, Typography } from '@mui/material';
import { useSuspenseQuery } from '@tanstack/react-query';
import React from 'react';

import { api } from '@/api/client';
import type { Application, Handoff, Tenant, UsageSummary } from '@/api/types';
import { useAuth } from '@/auth/AuthProvider';
import PageHeader from '@/components/PageHeader';
import { useI18n } from '@/i18n/I18nProvider';

const DashboardPage: React.FC = () => {
  const { user } = useAuth();
  if (user?.is_platform_admin && !user.tenant_id) return <PlatformOverview />;
  return user?.role === 'agent' ? <AgentOverview /> : <TenantOverview />;
};

const PlatformOverview: React.FC = () => {
  const { messages } = useI18n();
  const { data: tenants } = useSuspenseQuery({
    queryKey: ['tenants'],
    queryFn: () => api<Tenant[]>('/v1/platform/tenants'),
  });
  return (
    <>
      <PageHeader title={messages.dashboard.platformTitle} description={messages.dashboard.platformDescription} />
      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, 1fr)' } }}>
        <Paper variant="outlined" sx={{ p: 3 }}><Typography color="text.secondary" fontSize={13}>{messages.dashboard.totalTenants}</Typography><Typography fontSize={32} fontWeight={750}>{tenants.length}</Typography></Paper>
        <Paper variant="outlined" sx={{ p: 3 }}><Typography color="text.secondary" fontSize={13}>{messages.dashboard.activeTenants}</Typography><Typography fontSize={32} fontWeight={750}>{tenants.filter((tenant) => tenant.status === 'active').length}</Typography></Paper>
      </Box>
    </>
  );
};

const TenantOverview: React.FC = () => {
  const { language, messages } = useI18n();
  const { data: applications } = useSuspenseQuery({
    queryKey: ['applications'],
    queryFn: () => api<Application[]>('/v1/admin/applications'),
  });
  const { data: usage } = useSuspenseQuery({
    queryKey: ['usage-summary'],
    queryFn: () => api<UsageSummary>('/v1/admin/usage/summary'),
  });
  const { data: pending } = useSuspenseQuery({
    queryKey: ['handoffs', 'pending'],
    queryFn: () => api<Handoff[]>('/v1/admin/handoffs?status=pending'),
  });
  const metrics = [
    { label: messages.dashboard.applications, value: applications.length, icon: AppWindow, color: '#147a5b' },
    { label: messages.dashboard.aiRequests, value: usage.total_requests, icon: Activity, color: '#3367a8' },
    { label: messages.dashboard.failedRequests, value: usage.failed_requests, icon: CircleAlert, color: '#b14a3c' },
    { label: messages.dashboard.waitingHandoffs, value: pending.length, icon: Headphones, color: '#ba6a12' },
  ];
  return (
    <>
      <PageHeader title={messages.dashboard.tenantTitle} description={messages.dashboard.tenantDescription} />
      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, 1fr)', xl: 'repeat(4, 1fr)' } }}>
        {metrics.map((metric) => (
          <Paper key={metric.label} variant="outlined" sx={{ alignItems: 'center', display: 'flex', gap: 2, p: 2.5 }}>
            <Box sx={{ alignItems: 'center', bgcolor: `${metric.color}18`, borderRadius: 1, color: metric.color, display: 'flex', height: 42, justifyContent: 'center', width: 42 }}>
              <metric.icon size={20} />
            </Box>
            <Box>
              <Typography color="text.secondary" fontSize={12}>{metric.label}</Typography>
              <Typography fontSize={24} fontWeight={750}>{metric.value.toLocaleString(language)}</Typography>
            </Box>
          </Paper>
        ))}
      </Box>
    </>
  );
};

const AgentOverview: React.FC = () => {
  const { messages } = useI18n();
  const { data: pending } = useSuspenseQuery({
    queryKey: ['handoffs', 'pending'],
    queryFn: () => api<Handoff[]>('/v1/admin/handoffs?status=pending'),
  });
  return (
    <>
      <PageHeader title={messages.dashboard.agentTitle} description={messages.dashboard.agentDescription} />
      <Paper variant="outlined" sx={{ p: 3 }}>
        <Typography color="text.secondary" fontSize={13}>{messages.dashboard.waitingConversations}</Typography>
        <Typography fontSize={32} fontWeight={750} sx={{ mt: 0.5 }}>{pending.length}</Typography>
      </Paper>
    </>
  );
};

export default DashboardPage;
