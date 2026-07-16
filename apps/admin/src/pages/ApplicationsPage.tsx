import { Copy, KeyRound, Pencil, Plus, Power, ShieldX } from 'lucide-react';
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
import { useMutation, useQuery, useQueryClient, useSuspenseQuery } from '@tanstack/react-query';
import React, { useCallback, useState } from 'react';

import { api, errorMessage } from '@/api/client';
import type { ApiCredential, Application } from '@/api/types';
import PageHeader from '@/components/PageHeader';

interface CredentialCreated {
  id: string;
  key_prefix: string;
  api_key: string;
  created_at: string;
}

const ApplicationsPage: React.FC = () => {
  const queryClient = useQueryClient();
  const { data } = useSuspenseQuery({
    queryKey: ['applications'],
    queryFn: () => api<Application[]>('/v1/admin/applications'),
  });
  const [createOpen, setCreateOpen] = useState(false);
  const [name, setName] = useState('');
  const [origins, setOrigins] = useState('');
  const [credential, setCredential] = useState<CredentialCreated | null>(null);
  const [credentialApplication, setCredentialApplication] = useState<Application | null>(null);
  const [editing, setEditing] = useState<Application | null>(null);
  const [editName, setEditName] = useState('');
  const [editOrigins, setEditOrigins] = useState('');
  const [editRateLimit, setEditRateLimit] = useState('60');
  const [error, setError] = useState<string | null>(null);
  const { data: credentials = [], isFetching: credentialsLoading } = useQuery({
    queryKey: ['application-credentials', credentialApplication?.id],
    queryFn: () => api<ApiCredential[]>(
      `/v1/admin/applications/${credentialApplication?.id}/credentials`,
    ),
    enabled: credentialApplication !== null,
  });

  const create = useMutation({
    mutationFn: () => api<Application>('/v1/admin/applications', {
      method: 'POST',
      body: JSON.stringify({
        name,
        allowed_origins: origins.split('\n').map((item) => item.trim()).filter(Boolean),
      }),
    }),
    onSuccess: async () => {
      setCreateOpen(false);
      setName('');
      setOrigins('');
      await queryClient.invalidateQueries({ queryKey: ['applications'] });
    },
    onError: (cause) => setError(errorMessage(cause)),
  });

  const createCredential = useCallback(async (applicationId: string) => {
    setError(null);
    try {
      setCredential(await api<CredentialCreated>(
        `/v1/admin/applications/${applicationId}/credentials`,
        { method: 'POST', body: JSON.stringify({ scopes: ['customer_token:create'] }) },
      ));
      await queryClient.invalidateQueries({
        queryKey: ['application-credentials', applicationId],
      });
    } catch (cause) {
      setError(errorMessage(cause));
    }
  }, [queryClient]);

  const revokeCredential = useCallback(async (credentialId: string) => {
    if (!credentialApplication) return;
    setError(null);
    try {
      await api(
        `/v1/admin/applications/${credentialApplication.id}/credentials/${credentialId}`,
        { method: 'DELETE' },
      );
      await queryClient.invalidateQueries({
        queryKey: ['application-credentials', credentialApplication.id],
      });
    } catch (cause) {
      setError(errorMessage(cause));
    }
  }, [credentialApplication, queryClient]);

  const toggleApplication = useCallback(async (application: Application) => {
    setError(null);
    try {
      await api(`/v1/admin/applications/${application.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ status: application.status === 'active' ? 'disabled' : 'active' }),
      });
      await queryClient.invalidateQueries({ queryKey: ['applications'] });
    } catch (cause) {
      setError(errorMessage(cause));
    }
  }, [queryClient]);

  const openEdit = useCallback((application: Application) => {
    setEditing(application);
    setEditName(application.name);
    setEditOrigins(application.allowed_origins.join('\n'));
    setEditRateLimit(String(application.rate_limit_per_minute));
    setError(null);
  }, []);

  const saveEdit = useCallback(async () => {
    if (!editing) return;
    setError(null);
    try {
      await api(`/v1/admin/applications/${editing.id}`, {
        method: 'PATCH',
        body: JSON.stringify({
          name: editName,
          allowed_origins: editOrigins.split('\n').map((item) => item.trim()).filter(Boolean),
          rate_limit_per_minute: Number(editRateLimit),
        }),
      });
      setEditing(null);
      await queryClient.invalidateQueries({ queryKey: ['applications'] });
    } catch (cause) {
      setError(errorMessage(cause));
    }
  }, [editName, editOrigins, editRateLimit, editing, queryClient]);

  return (
    <>
      <PageHeader
        title="Applications"
        description="Public integration identities, origins, limits, and server credentials."
        action={{ label: 'New application', icon: Plus, onClick: () => setCreateOpen(true) }}
      />
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
      <TableContainer component={Paper} variant="outlined">
        <Table>
          <TableHead>
            <TableRow>
              <TableCell>Name</TableCell>
              <TableCell>Public key</TableCell>
              <TableCell>Allowed origins</TableCell>
              <TableCell>Rate limit</TableCell>
              <TableCell>Status</TableCell>
              <TableCell align="right">Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {data.map((application) => (
              <TableRow key={application.id} hover>
                <TableCell><Typography fontWeight={650}>{application.name}</Typography></TableCell>
                <TableCell><Typography component="code" fontSize={12}>{application.public_key}</Typography></TableCell>
                <TableCell>{application.allowed_origins.length ? application.allowed_origins.join(', ') : 'None'}</TableCell>
                <TableCell>{application.rate_limit_per_minute}/min</TableCell>
                <TableCell><Chip size="small" color={application.status === 'active' ? 'success' : 'default'} label={application.status} /></TableCell>
                <TableCell align="right">
                  <Tooltip title="Edit application">
                    <IconButton aria-label={`Edit ${application.name}`} onClick={() => openEdit(application)}><Pencil size={17} /></IconButton>
                  </Tooltip>
                  <Tooltip title="Create server credential">
                    <IconButton onClick={() => setCredentialApplication(application)}><KeyRound size={17} /></IconButton>
                  </Tooltip>
                  <Tooltip title={application.status === 'active' ? 'Disable application' : 'Enable application'}>
                    <IconButton onClick={() => void toggleApplication(application)}><Power size={17} /></IconButton>
                  </Tooltip>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>

      <Dialog open={createOpen} onClose={() => setCreateOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>New application</DialogTitle>
        <DialogContent sx={{ display: 'grid', gap: 2, pt: '8px !important' }}>
          <TextField label="Name" value={name} onChange={(event) => setName(event.target.value)} required />
          <TextField label="Allowed origins" value={origins} onChange={(event) => setOrigins(event.target.value)} multiline minRows={3} placeholder="https://example.com" helperText="One exact HTTP(S) origin per line" />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCreateOpen(false)}>Cancel</Button>
          <Button variant="contained" disabled={!name.trim() || create.isPending} onClick={() => create.mutate()}>Create</Button>
        </DialogActions>
      </Dialog>

      <Dialog
        open={credentialApplication !== null}
        onClose={() => setCredentialApplication(null)}
        fullWidth
        maxWidth="md"
      >
        <DialogTitle>Server credentials · {credentialApplication?.name}</DialogTitle>
        <DialogContent>
          <Alert severity="info" sx={{ mb: 2 }}>
            Secrets are shown only at creation. Existing credentials are identified by prefix.
          </Alert>
          <TableContainer variant="outlined" component={Paper}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Prefix</TableCell>
                  <TableCell>Scopes</TableCell>
                  <TableCell>Created</TableCell>
                  <TableCell>Status</TableCell>
                  <TableCell align="right">Action</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {credentials.map((item) => (
                  <TableRow key={item.id}>
                    <TableCell><Typography component="code" fontSize={12}>{item.key_prefix}</Typography></TableCell>
                    <TableCell>{item.scopes.join(', ')}</TableCell>
                    <TableCell>{new Date(item.created_at).toLocaleDateString()}</TableCell>
                    <TableCell>
                      <Chip
                        size="small"
                        color={item.revoked_at ? 'default' : 'success'}
                        label={item.revoked_at ? 'revoked' : 'active'}
                      />
                    </TableCell>
                    <TableCell align="right">
                      <Tooltip title={item.revoked_at ? 'Credential already revoked' : 'Revoke credential'}>
                        <span>
                          <IconButton
                            aria-label={`Revoke credential ${item.key_prefix}`}
                            color="error"
                            disabled={item.revoked_at !== null}
                            onClick={() => void revokeCredential(item.id)}
                          >
                            <ShieldX size={17} />
                          </IconButton>
                        </span>
                      </Tooltip>
                    </TableCell>
                  </TableRow>
                ))}
                {!credentialsLoading && credentials.length === 0 && (
                  <TableRow><TableCell colSpan={5}>No server credentials created.</TableCell></TableRow>
                )}
              </TableBody>
            </Table>
          </TableContainer>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCredentialApplication(null)}>Close</Button>
          <Button
            variant="contained"
            startIcon={<Plus size={16} />}
            onClick={() => credentialApplication && void createCredential(credentialApplication.id)}
          >
            Create credential
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={editing !== null} onClose={() => setEditing(null)} fullWidth maxWidth="sm">
        <DialogTitle>Edit application</DialogTitle>
        <DialogContent sx={{ display: 'grid', gap: 2, pt: '8px !important' }}>
          <TextField label="Name" value={editName} onChange={(event) => setEditName(event.target.value)} required />
          <TextField label="Allowed origins" value={editOrigins} onChange={(event) => setEditOrigins(event.target.value)} multiline minRows={3} placeholder="https://example.com" helperText="One exact HTTP(S) origin per line" />
          <TextField label="Customer write requests per minute" type="number" value={editRateLimit} onChange={(event) => setEditRateLimit(event.target.value)} inputProps={{ min: 1, max: 10000 }} />
        </DialogContent>
        <DialogActions><Button onClick={() => setEditing(null)}>Cancel</Button><Button variant="contained" disabled={!editName.trim() || Number(editRateLimit) < 1 || Number(editRateLimit) > 10000} onClick={() => void saveEdit()}>Save</Button></DialogActions>
      </Dialog>

      <Dialog open={credential !== null} onClose={() => setCredential(null)} fullWidth maxWidth="sm">
        <DialogTitle>Server credential</DialogTitle>
        <DialogContent>
          <Alert severity="warning" sx={{ mb: 2 }}>This credential is shown once. Store it only in the integrating server.</Alert>
          <Box sx={{ alignItems: 'center', bgcolor: 'grey.100', border: 1, borderColor: 'divider', borderRadius: 1, display: 'flex', gap: 1, p: 1.5 }}>
            <Typography component="code" fontSize={12} sx={{ flex: 1, overflowWrap: 'anywhere' }}>{credential?.api_key}</Typography>
            <Tooltip title="Copy credential">
              <IconButton onClick={() => void navigator.clipboard.writeText(credential?.api_key ?? '')}><Copy size={17} /></IconButton>
            </Tooltip>
          </Box>
        </DialogContent>
        <DialogActions><Button variant="contained" onClick={() => setCredential(null)}>Done</Button></DialogActions>
      </Dialog>
    </>
  );
};

export default ApplicationsPage;
