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

const PlatformPage: React.FC = () => {
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
    } catch (cause) { setError(errorMessage(cause)); } finally { setBusy(false); }
  }, [name, refresh, slug]);
  const toggle = useCallback(async (tenant: Tenant) => {
    setBusy(true); setError(null);
    try {
      await api(`/v1/platform/tenants/${tenant.id}`, { method: 'PATCH', body: JSON.stringify({ status: tenant.status === 'active' ? 'disabled' : 'active' }) });
      await refresh();
    } catch (cause) { setError(errorMessage(cause)); } finally { setBusy(false); }
  }, [refresh]);
  const createAdmin = useCallback(async () => {
    if (!adminTenant) return;
    setBusy(true); setError(null);
    try {
      await api(`/v1/platform/tenants/${adminTenant.id}/admins`, { method: 'POST', body: JSON.stringify({ email: adminEmail, display_name: adminName, temporary_password: password }) });
      setAdminTenant(null); setAdminEmail(''); setAdminName(''); setPassword('');
    } catch (cause) { setError(errorMessage(cause)); } finally { setBusy(false); }
  }, [adminEmail, adminName, adminTenant, password]);

  return (
    <>
      <PageHeader title="Tenants" description="Provision and control isolated customer environments." action={{ label: 'New tenant', icon: Plus, onClick: () => setTenantOpen(true) }} />
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
      <TableContainer component={Paper} variant="outlined"><Table><TableHead><TableRow><TableCell>Tenant</TableCell><TableCell>Slug</TableCell><TableCell>Created</TableCell><TableCell>Status</TableCell><TableCell align="right">Actions</TableCell></TableRow></TableHead><TableBody>{data.map((tenant) => <TableRow key={tenant.id} hover><TableCell><Typography fontWeight={650}>{tenant.name}</Typography><Typography color="text.secondary" fontSize={11}>{tenant.id}</Typography></TableCell><TableCell>{tenant.slug}</TableCell><TableCell>{new Date(tenant.created_at).toLocaleDateString()}</TableCell><TableCell><Chip size="small" color={tenant.status === 'active' ? 'success' : 'default'} label={tenant.status} /></TableCell><TableCell align="right"><Tooltip title="Create tenant administrator"><IconButton onClick={() => setAdminTenant(tenant)}><UserPlus size={17} /></IconButton></Tooltip><Tooltip title={tenant.status === 'active' ? 'Disable tenant' : 'Enable tenant'}><IconButton disabled={busy} onClick={() => void toggle(tenant)}><Power size={17} /></IconButton></Tooltip></TableCell></TableRow>)}</TableBody></Table></TableContainer>
      <Dialog open={tenantOpen} onClose={() => setTenantOpen(false)} fullWidth maxWidth="sm"><DialogTitle>New tenant</DialogTitle><DialogContent sx={{ display: 'grid', gap: 2, pt: '8px !important' }}><TextField label="Name" value={name} onChange={(event) => setName(event.target.value)} /><TextField label="Slug" value={slug} onChange={(event) => setSlug(event.target.value)} helperText="Lowercase letters, numbers, and hyphens" /></DialogContent><DialogActions><Button onClick={() => setTenantOpen(false)}>Cancel</Button><Button variant="contained" disabled={!name.trim() || !slug.trim() || busy} onClick={() => void createTenant()}>Create</Button></DialogActions></Dialog>
      <Dialog open={adminTenant !== null} onClose={() => setAdminTenant(null)} fullWidth maxWidth="sm"><DialogTitle>Create administrator</DialogTitle><DialogContent sx={{ display: 'grid', gap: 2, pt: '8px !important' }}><Box><Typography fontWeight={650}>{adminTenant?.name}</Typography><Typography color="text.secondary" fontSize={12}>The administrator signs in with this tenant ID.</Typography></Box><TextField label="Display name" value={adminName} onChange={(event) => setAdminName(event.target.value)} /><TextField label="Email" type="email" value={adminEmail} onChange={(event) => setAdminEmail(event.target.value)} /><TextField label="Temporary password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} helperText="At least 12 characters" /></DialogContent><DialogActions><Button onClick={() => setAdminTenant(null)}>Cancel</Button><Button variant="contained" disabled={!adminName.trim() || !adminEmail.trim() || password.length < 12 || busy} onClick={() => void createAdmin()}>Create admin</Button></DialogActions></Dialog>
    </>
  );
};

export default PlatformPage;
