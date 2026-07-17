import { Plus, Power, UserPlus } from 'lucide-react';
import {
  Alert,
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import { useQueryClient, useSuspenseQuery } from '@tanstack/react-query';
import React, { useCallback, useState } from 'react';

import { api, errorMessage } from '@/api/client';
import type { Tenant } from '@/api/types';
import PageHeader from '@/components/PageHeader';
import { useI18n } from '@/i18n/I18nProvider';

const PlatformPage: React.FC = () => {
  const { labelValue, language, messages } = useI18n();
  const queryClient = useQueryClient();
  const { data } = useSuspenseQuery({
    queryKey: ['tenants'],
    queryFn: () => api<Tenant[]>('/v1/platform/tenants'),
  });
  const [tenantOpen, setTenantOpen] = useState(false);
  const [adminTenant, setAdminTenant] = useState<Tenant | null>(null);
  const [name, setName] = useState('');
  const [slug, setSlug] = useState('');
  const [adminName, setAdminName] = useState('');
  const [adminEmail, setAdminEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => queryClient.invalidateQueries({ queryKey: ['tenants'] }), [queryClient]);
  const createTenant = useCallback(async () => {
    setBusy(true); setError(null);
    try {
      await api('/v1/platform/tenants', { method: 'POST', body: JSON.stringify({ name, slug }) });
      setTenantOpen(false); setName(''); setSlug(''); await refresh();
    } catch (cause) { setError(errorMessage(cause, messages.common.requestFailed)); } finally { setBusy(false); }
  }, [messages.common.requestFailed, name, refresh, slug]);
  const toggle = useCallback(async (tenant: Tenant) => {
    setBusy(true); setError(null);
    try {
      await api(`/v1/platform/tenants/${tenant.id}`, { method: 'PATCH', body: JSON.stringify({ status: tenant.status === 'active' ? 'disabled' : 'active' }) });
      await refresh();
    } catch (cause) { setError(errorMessage(cause, messages.common.requestFailed)); } finally { setBusy(false); }
  }, [messages.common.requestFailed, refresh]);
  const createAdmin = useCallback(async () => {
    if (!adminTenant) return;
    setBusy(true); setError(null);
    try {
      await api(`/v1/platform/tenants/${adminTenant.id}/admins`, { method: 'POST', body: JSON.stringify({ email: adminEmail, display_name: adminName, temporary_password: password }) });
      setAdminTenant(null); setAdminEmail(''); setAdminName(''); setPassword('');
    } catch (cause) { setError(errorMessage(cause, messages.common.requestFailed)); } finally { setBusy(false); }
  }, [adminEmail, adminName, adminTenant, messages.common.requestFailed, password]);

  return (
    <>
      <PageHeader title={messages.platform.title} description={messages.platform.description} action={{ label: messages.platform.newTenant, icon: Plus, onClick: () => setTenantOpen(true) }} />
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
      <TableContainer component={Paper} variant="outlined"><Table><TableHead><TableRow><TableCell>{messages.platform.tenant}</TableCell><TableCell>{messages.platform.slug}</TableCell><TableCell>{messages.common.created}</TableCell><TableCell>{messages.common.status}</TableCell><TableCell align="right">{messages.common.actions}</TableCell></TableRow></TableHead><TableBody>{data.map((tenant) => <TableRow key={tenant.id} hover><TableCell><Typography fontWeight={650}>{tenant.name}</Typography><Typography color="text.secondary" fontSize={11}>{tenant.id}</Typography></TableCell><TableCell>{tenant.slug}</TableCell><TableCell>{new Date(tenant.created_at).toLocaleDateString(language)}</TableCell><TableCell><Chip size="small" color={tenant.status === 'active' ? 'success' : 'default'} label={labelValue(tenant.status)} /></TableCell><TableCell align="right"><Tooltip title={messages.platform.createTenantAdmin}><IconButton aria-label={messages.platform.createTenantAdmin} onClick={() => setAdminTenant(tenant)}><UserPlus size={17} /></IconButton></Tooltip><Tooltip title={tenant.status === 'active' ? messages.platform.disableTenant : messages.platform.enableTenant}><IconButton aria-label={tenant.status === 'active' ? messages.platform.disableTenant : messages.platform.enableTenant} disabled={busy} onClick={() => void toggle(tenant)}><Power size={17} /></IconButton></Tooltip></TableCell></TableRow>)}</TableBody></Table></TableContainer>
      <Dialog open={tenantOpen} onClose={() => setTenantOpen(false)} fullWidth maxWidth="sm"><DialogTitle>{messages.platform.newTenant}</DialogTitle><DialogContent sx={{ display: 'grid', gap: 2, pt: '8px !important' }}><TextField label={messages.common.name} value={name} onChange={(event) => setName(event.target.value)} /><TextField label={messages.platform.slug} value={slug} onChange={(event) => setSlug(event.target.value)} helperText={messages.platform.slugHelp} /></DialogContent><DialogActions><Button onClick={() => setTenantOpen(false)}>{messages.common.cancel}</Button><Button variant="contained" disabled={!name.trim() || !slug.trim() || busy} onClick={() => void createTenant()}>{messages.common.create}</Button></DialogActions></Dialog>
      <Dialog open={adminTenant !== null} onClose={() => setAdminTenant(null)} fullWidth maxWidth="sm"><DialogTitle>{messages.platform.createAdministrator}</DialogTitle><DialogContent sx={{ display: 'grid', gap: 2, pt: '8px !important' }}><Box><Typography fontWeight={650}>{adminTenant?.name}</Typography><Typography color="text.secondary" fontSize={12}>{messages.platform.administratorTenantHelp}</Typography></Box><TextField label={messages.team.displayName} value={adminName} onChange={(event) => setAdminName(event.target.value)} /><TextField label={messages.common.email} type="email" value={adminEmail} onChange={(event) => setAdminEmail(event.target.value)} /><TextField label={messages.team.temporaryPassword} type="password" value={password} onChange={(event) => setPassword(event.target.value)} helperText={messages.team.passwordHelp} /></DialogContent><DialogActions><Button onClick={() => setAdminTenant(null)}>{messages.common.cancel}</Button><Button variant="contained" disabled={!adminName.trim() || !adminEmail.trim() || password.length < 12 || busy} onClick={() => void createAdmin()}>{messages.platform.createAdmin}</Button></DialogActions></Dialog>
    </>
  );
};

export default PlatformPage;
