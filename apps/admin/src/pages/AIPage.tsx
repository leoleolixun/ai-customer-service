import { CheckCircle2, Plus, Power, ServerCog } from 'lucide-react';
import {
  Alert,
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import { useQueryClient, useSuspenseQuery } from '@tanstack/react-query';
import React, { useCallback, useState } from 'react';

import { api, errorMessage } from '@/api/client';
import type { Application, ModelConfig, ProviderAccount } from '@/api/types';
import PageHeader from '@/components/PageHeader';

const AIPage: React.FC = () => {
  const queryClient = useQueryClient();
  const { data: accounts } = useSuspenseQuery({
    queryKey: ['provider-accounts'],
    queryFn: () => api<ProviderAccount[]>('/v1/admin/ai/provider-accounts'),
  });
  const { data: models } = useSuspenseQuery({
    queryKey: ['model-configs'],
    queryFn: () => api<ModelConfig[]>('/v1/admin/ai/model-configs'),
  });
  const { data: applications } = useSuspenseQuery({
    queryKey: ['applications'],
    queryFn: () => api<Application[]>('/v1/admin/applications'),
  });
  const [providerOpen, setProviderOpen] = useState(false);
  const [modelOpen, setModelOpen] = useState(false);
  const [activateModel, setActivateModel] = useState<ModelConfig | null>(null);
  const [applicationId, setApplicationId] = useState('');
  const [providerName, setProviderName] = useState('');
  const [providerKind, setProviderKind] = useState<ProviderAccount['kind']>('fake');
  const [baseUrl, setBaseUrl] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [modelName, setModelName] = useState('');
  const [providerId, setProviderId] = useState('');
  const [remoteModelName, setRemoteModelName] = useState('');
  const [purpose, setPurpose] = useState<ModelConfig['purpose']>('chat');
  const [dimension, setDimension] = useState('1024');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['provider-accounts'] }),
      queryClient.invalidateQueries({ queryKey: ['model-configs'] }),
    ]);
  }, [queryClient]);

  const createProvider = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      await api('/v1/admin/ai/provider-accounts', {
        method: 'POST',
        body: JSON.stringify({
          name: providerName,
          kind: providerKind,
          base_url: providerKind === 'openai_compatible' ? baseUrl : null,
          api_key: providerKind === 'openai_compatible' ? apiKey : null,
        }),
      });
      setProviderOpen(false);
      setProviderName('');
      setApiKey('');
      await refresh();
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }, [apiKey, baseUrl, providerKind, providerName, refresh]);

  const testProvider = useCallback(async (accountId: string) => {
    setBusy(true);
    setError(null);
    try {
      await api(`/v1/admin/ai/provider-accounts/${accountId}/test`, { method: 'POST' });
      await refresh();
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }, [refresh]);

  const createModel = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      await api('/v1/admin/ai/model-configs', {
        method: 'POST',
        body: JSON.stringify({
          provider_account_id: providerId,
          name: modelName,
          model_name: remoteModelName,
          purpose,
          embedding_dimension: purpose === 'embedding' ? Number(dimension) : null,
        }),
      });
      setModelOpen(false);
      setModelName('');
      setRemoteModelName('');
      await refresh();
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }, [dimension, modelName, providerId, purpose, refresh, remoteModelName]);

  const activate = useCallback(async () => {
    if (!activateModel || !applicationId) return;
    setBusy(true);
    setError(null);
    try {
      await api(`/v1/admin/ai/model-configs/${activateModel.id}/activate`, {
        method: 'POST',
        body: JSON.stringify({ application_id: applicationId }),
      });
      setActivateModel(null);
      setApplicationId('');
      await refresh();
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }, [activateModel, applicationId, refresh]);

  const deactivate = useCallback(async (model: ModelConfig) => {
    setBusy(true);
    setError(null);
    try {
      await api(`/v1/admin/ai/model-configs/${model.id}/deactivate`, { method: 'POST' });
      await refresh();
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }, [refresh]);

  return (
    <>
      <PageHeader title="AI models" description="Provider credentials stay encrypted; only tested providers can be used." />
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      <Box component="section" sx={{ mb: 4 }}>
        <Box sx={{ alignItems: 'center', display: 'flex', justifyContent: 'space-between', mb: 1.5 }}>
          <Typography component="h2" variant="h2">Provider accounts</Typography>
          <Button startIcon={<Plus size={16} />} onClick={() => setProviderOpen(true)}>Add provider</Button>
        </Box>
        <TableContainer component={Paper} variant="outlined">
          <Table>
            <TableHead><TableRow><TableCell>Name</TableCell><TableCell>Kind</TableCell><TableCell>Endpoint</TableCell><TableCell>Status</TableCell><TableCell align="right">Action</TableCell></TableRow></TableHead>
            <TableBody>
              {accounts.map((account) => (
                <TableRow key={account.id} hover>
                  <TableCell><Typography fontWeight={650}>{account.name}</Typography></TableCell>
                  <TableCell>{account.kind.replace('_', ' ')}</TableCell>
                  <TableCell>{account.base_url ?? 'Built-in deterministic provider'}</TableCell>
                  <TableCell><Chip size="small" color={account.status === 'ready' ? 'success' : 'default'} label={account.status} /></TableCell>
                  <TableCell align="right"><Button size="small" startIcon={<CheckCircle2 size={15} />} disabled={busy} onClick={() => void testProvider(account.id)}>Test</Button></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      </Box>

      <Box component="section">
        <Box sx={{ alignItems: 'center', display: 'flex', justifyContent: 'space-between', mb: 1.5 }}>
          <Typography component="h2" variant="h2">Model configurations</Typography>
          <Button startIcon={<Plus size={16} />} onClick={() => setModelOpen(true)}>Add model</Button>
        </Box>
        <TableContainer component={Paper} variant="outlined">
          <Table>
            <TableHead><TableRow><TableCell>Name</TableCell><TableCell>Remote model</TableCell><TableCell>Purpose</TableCell><TableCell>Dimension</TableCell><TableCell>Status</TableCell><TableCell align="right">Action</TableCell></TableRow></TableHead>
            <TableBody>
              {models.map((model) => (
                <TableRow key={model.id} hover>
                  <TableCell><Typography fontWeight={650}>{model.name}</Typography></TableCell>
                  <TableCell>{model.model_name}</TableCell><TableCell>{model.purpose}</TableCell><TableCell>{model.embedding_dimension ?? '—'}</TableCell>
                  <TableCell><Chip size="small" color={model.status === 'active' ? 'success' : 'default'} label={model.status} /></TableCell>
                  <TableCell align="right">{model.purpose === 'chat' && (model.status === 'active' ? <Button size="small" color="error" startIcon={<Power size={15} />} disabled={busy} onClick={() => void deactivate(model)}>Deactivate</Button> : <Button size="small" startIcon={<Power size={15} />} disabled={busy} onClick={() => setActivateModel(model)}>Activate</Button>)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      </Box>

      <Dialog open={providerOpen} onClose={() => setProviderOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>Add provider account</DialogTitle>
        <DialogContent sx={{ display: 'grid', gap: 2, pt: '8px !important' }}>
          <TextField label="Name" value={providerName} onChange={(event) => setProviderName(event.target.value)} required />
          <FormControl><InputLabel>Provider kind</InputLabel><Select label="Provider kind" value={providerKind} onChange={(event) => setProviderKind(event.target.value as ProviderAccount['kind'])}><MenuItem value="fake">Fake (test only)</MenuItem><MenuItem value="openai_compatible">OpenAI compatible</MenuItem></Select></FormControl>
          {providerKind === 'openai_compatible' && <><TextField label="Base URL" value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} placeholder="https://api.example.com/v1" required /><TextField label="API key" type="password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} required /></>}
        </DialogContent>
        <DialogActions><Button onClick={() => setProviderOpen(false)}>Cancel</Button><Button variant="contained" startIcon={<ServerCog size={16} />} disabled={!providerName.trim() || busy} onClick={() => void createProvider()}>Save provider</Button></DialogActions>
      </Dialog>

      <Dialog open={modelOpen} onClose={() => setModelOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>Add model configuration</DialogTitle>
        <DialogContent sx={{ display: 'grid', gap: 2, pt: '8px !important' }}>
          <FormControl><InputLabel>Provider</InputLabel><Select label="Provider" value={providerId} onChange={(event) => setProviderId(event.target.value)}>{accounts.filter((account) => account.status === 'ready').map((account) => <MenuItem key={account.id} value={account.id}>{account.name}</MenuItem>)}</Select></FormControl>
          <TextField label="Configuration name" value={modelName} onChange={(event) => setModelName(event.target.value)} required />
          <TextField label="Remote model name" value={remoteModelName} onChange={(event) => setRemoteModelName(event.target.value)} required />
          <FormControl><InputLabel>Purpose</InputLabel><Select label="Purpose" value={purpose} onChange={(event) => setPurpose(event.target.value as ModelConfig['purpose'])}><MenuItem value="chat">Chat</MenuItem><MenuItem value="embedding">Embedding</MenuItem></Select></FormControl>
          {purpose === 'embedding' && <TextField label="Embedding dimension" type="number" value={dimension} onChange={(event) => setDimension(event.target.value)} inputProps={{ min: 8, max: 16384 }} />}
        </DialogContent>
        <DialogActions><Button onClick={() => setModelOpen(false)}>Cancel</Button><Button variant="contained" disabled={!providerId || !modelName.trim() || !remoteModelName.trim() || busy} onClick={() => void createModel()}>Save model</Button></DialogActions>
      </Dialog>

      <Dialog open={activateModel !== null} onClose={() => setActivateModel(null)} fullWidth maxWidth="xs">
        <DialogTitle>Activate chat model</DialogTitle>
        <DialogContent sx={{ pt: '8px !important' }}><FormControl fullWidth><InputLabel>Application</InputLabel><Select label="Application" value={applicationId} onChange={(event) => setApplicationId(event.target.value)}>{applications.filter((application) => application.status === 'active').map((application) => <MenuItem key={application.id} value={application.id}>{application.name}</MenuItem>)}</Select></FormControl></DialogContent>
        <DialogActions><Button onClick={() => setActivateModel(null)}>Cancel</Button><Button variant="contained" disabled={!applicationId || busy} onClick={() => void activate()}>Activate</Button></DialogActions>
      </Dialog>
    </>
  );
};

export default AIPage;
