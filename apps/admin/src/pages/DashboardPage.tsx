import { Activity, AppWindow, CircleAlert, Headphones } from 'lucide-react';
import { Box, Paper, Typography } from '@mui/material';
import { useSuspenseQuery } from '@tanstack/react-query';
import React from 'react';

import { api } from '@/api/client';
import type { Application, Handoff, Tenant, UsageSummary } from '@/api/types';
import { useAuth } from '@/auth/AuthProvider';
import PageHeader from '@/components/PageHeader';

const DashboardPage: React.FC = () => {
  const { user } = useAuth();
  if (user?.is_platform_admin && !user.tenant_id) return <PlatformOverview />;
  return user?.role === 'agent' ? <AgentOverview /> : <TenantOverview />;
};

const PlatformOverview: React.FC = () => {
  const { data: tenants } = useSuspenseQuery({
    queryKey: ['tenants'],
    queryFn: () => api<Tenant[]>('/v1/platform/tenants'),
  });
  return (
    <>
      <PageHeader title="Platform overview" description="Tenant lifecycle and platform access." />
      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, 1fr)' } }}>
        <Paper variant="outlined" sx={{ p: 3 }}><Typography color="text.secondary" fontSize={13}>Total tenants</Typography><Typography fontSize={32} fontWeight={750}>{tenants.length}</Typography></Paper>
        <Paper variant="outlined" sx={{ p: 3 }}><Typography color="text.secondary" fontSize={13}>Active tenants</Typography><Typography fontSize={32} fontWeight={750}>{tenants.filter((tenant) => tenant.status === 'active').length}</Typography></Paper>
      </Box>
    </>
  );
};

const TenantOverview: React.FC = () => {
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
    { label: 'Applications', value: applications.length, icon: AppWindow, color: '#147a5b' },
    { label: 'AI requests', value: usage.total_requests, icon: Activity, color: '#3367a8' },
    { label: 'Failed requests', value: usage.failed_requests, icon: CircleAlert, color: '#b14a3c' },
    { label: 'Waiting handoffs', value: pending.length, icon: Headphones, color: '#ba6a12' },
  ];
  return (
    <>
      <PageHeader title="Overview" description="Current tenant activity for the last 30 days." />
      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, 1fr)', xl: 'repeat(4, 1fr)' } }}>
        {metrics.map((metric) => (
          <Paper key={metric.label} variant="outlined" sx={{ alignItems: 'center', display: 'flex', gap: 2, p: 2.5 }}>
            <Box sx={{ alignItems: 'center', bgcolor: `${metric.color}18`, borderRadius: 1, color: metric.color, display: 'flex', height: 42, justifyContent: 'center', width: 42 }}>
              <metric.icon size={20} />
            </Box>
            <Box>
              <Typography color="text.secondary" fontSize={12}>{metric.label}</Typography>
              <Typography fontSize={24} fontWeight={750}>{metric.value.toLocaleString()}</Typography>
            </Box>
          </Paper>
        ))}
      </Box>
    </>
  );
};

const AgentOverview: React.FC = () => {
  const { data: pending } = useSuspenseQuery({
    queryKey: ['handoffs', 'pending'],
    queryFn: () => api<Handoff[]>('/v1/admin/handoffs?status=pending'),
  });
  return (
    <>
      <PageHeader title="Agent workspace" description="Conversations waiting for a human response." />
      <Paper variant="outlined" sx={{ p: 3 }}>
        <Typography color="text.secondary" fontSize={13}>Waiting conversations</Typography>
        <Typography fontSize={32} fontWeight={750} sx={{ mt: 0.5 }}>{pending.length}</Typography>
      </Paper>
    </>
  );
};

export default DashboardPage;
