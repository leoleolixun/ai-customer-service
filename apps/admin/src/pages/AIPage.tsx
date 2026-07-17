import { CheckCircle2, Pencil, Plus, Power, ServerCog, Trash2 } from 'lucide-react';
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
  IconButton,
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
  Tooltip,
  Typography,
} from '@mui/material';
import { useQueryClient, useSuspenseQuery } from '@tanstack/react-query';
import React, { useCallback, useState } from 'react';

import { api, errorMessage } from '@/api/client';
import type { Application, ModelConfig, ProviderAccount } from '@/api/types';
import PageHeader from '@/components/PageHeader';
import { useI18n } from '@/i18n/I18nProvider';

const AIPage: React.FC = () => {
  const { format, labelValue, messages } = useI18n();
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
  const [editingProvider, setEditingProvider] = useState<ProviderAccount | null>(null);
  const [providerToDelete, setProviderToDelete] = useState<ProviderAccount | null>(null);
  const [modelOpen, setModelOpen] = useState(false);
  const [activateModel, setActivateModel] = useState<ModelConfig | null>(null);
  const [applicationId, setApplicationId] = useState('');
  const [providerName, setProviderName] = useState('');
  const [providerKind, setProviderKind] = useState<ProviderAccount['kind']>('fake');
  const [baseUrl, setBaseUrl] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [editProviderName, setEditProviderName] = useState('');
  const [editBaseUrl, setEditBaseUrl] = useState('');
  const [replacementApiKey, setReplacementApiKey] = useState('');
  const [modelName, setModelName] = useState('');
  const [providerId, setProviderId] = useState('');
  const [remoteModelName, setRemoteModelName] = useState('');
  const [purpose, setPurpose] = useState<ModelConfig['purpose']>('chat');
  const [dimension, setDimension] = useState('1024');
  const [thinkingMode, setThinkingMode] = useState<ModelConfig['thinking_mode']>('provider_default');
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
      setError(errorMessage(cause, messages.common.requestFailed));
    } finally {
      setBusy(false);
    }
  }, [apiKey, baseUrl, messages.common.requestFailed, providerKind, providerName, refresh]);

  const testProvider = useCallback(async (accountId: string) => {
    setBusy(true);
    setError(null);
    try {
      await api(`/v1/admin/ai/provider-accounts/${accountId}/test`, { method: 'POST' });
      await refresh();
    } catch (cause) {
      setError(errorMessage(cause, messages.common.requestFailed));
    } finally {
      setBusy(false);
    }
  }, [messages.common.requestFailed, refresh]);

  const openProviderEditor = useCallback((account: ProviderAccount) => {
    setEditingProvider(account);
    setEditProviderName(account.name);
    setEditBaseUrl(account.base_url ?? '');
    setReplacementApiKey('');
    setError(null);
  }, []);

  const updateProvider = useCallback(async () => {
    if (!editingProvider) return;
    setBusy(true);
    setError(null);
    try {
      const body: Record<string, string> = { name: editProviderName.trim() };
      if (editingProvider.kind === 'openai_compatible') {
        body.base_url = editBaseUrl.trim();
        if (replacementApiKey.trim()) body.api_key = replacementApiKey.trim();
      }
      await api(`/v1/admin/ai/provider-accounts/${editingProvider.id}`, {
        method: 'PATCH',
        body: JSON.stringify(body),
      });
      setEditingProvider(null);
      setReplacementApiKey('');
      await refresh();
    } catch (cause) {
      setError(errorMessage(cause, messages.common.requestFailed));
    } finally {
      setBusy(false);
    }
  }, [editBaseUrl, editProviderName, editingProvider, messages.common.requestFailed, refresh, replacementApiKey]);

  const deleteProvider = useCallback(async () => {
    if (!providerToDelete) return;
    setBusy(true);
    setError(null);
    try {
      await api(`/v1/admin/ai/provider-accounts/${providerToDelete.id}`, {
        method: 'DELETE',
      });
      setProviderToDelete(null);
      await refresh();
    } catch (cause) {
      setError(errorMessage(cause, messages.common.requestFailed));
    } finally {
      setBusy(false);
    }
  }, [messages.common.requestFailed, providerToDelete, refresh]);

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
          thinking_mode: purpose === 'chat' ? thinkingMode : 'provider_default',
        }),
      });
      setModelOpen(false);
      setModelName('');
      setRemoteModelName('');
      setThinkingMode('provider_default');
      await refresh();
    } catch (cause) {
      setError(errorMessage(cause, messages.common.requestFailed));
    } finally {
      setBusy(false);
    }
  }, [dimension, messages.common.requestFailed, modelName, providerId, purpose, refresh, remoteModelName, thinkingMode]);

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
      setError(errorMessage(cause, messages.common.requestFailed));
    } finally {
      setBusy(false);
    }
  }, [activateModel, applicationId, messages.common.requestFailed, refresh]);

  const deactivate = useCallback(async (model: ModelConfig) => {
    setBusy(true);
    setError(null);
    try {
      await api(`/v1/admin/ai/model-configs/${model.id}/deactivate`, { method: 'POST' });
      await refresh();
    } catch (cause) {
      setError(errorMessage(cause, messages.common.requestFailed));
    } finally {
      setBusy(false);
    }
  }, [messages.common.requestFailed, refresh]);

  return (
    <>
      <PageHeader title={messages.ai.title} description={messages.ai.description} />
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      <Box component="section" sx={{ mb: 4 }}>
        <Box sx={{ alignItems: 'center', display: 'flex', justifyContent: 'space-between', mb: 1.5 }}>
          <Typography component="h2" variant="h2">{messages.ai.providerAccounts}</Typography>
          <Button startIcon={<Plus size={16} />} onClick={() => setProviderOpen(true)}>{messages.ai.addProvider}</Button>
        </Box>
        <TableContainer component={Paper} variant="outlined">
          <Table>
            <TableHead><TableRow><TableCell>{messages.common.name}</TableCell><TableCell>{messages.ai.kind}</TableCell><TableCell>{messages.ai.endpoint}</TableCell><TableCell>{messages.common.status}</TableCell><TableCell align="right">{messages.common.action}</TableCell></TableRow></TableHead>
            <TableBody>
              {accounts.map((account) => (
                <TableRow key={account.id} hover>
                  <TableCell><Typography fontWeight={650}>{account.name}</Typography></TableCell>
                  <TableCell>{labelValue(account.kind)}</TableCell>
                  <TableCell>{account.base_url ?? messages.ai.builtInProvider}</TableCell>
                  <TableCell><Chip size="small" color={account.status === 'ready' ? 'success' : 'default'} label={labelValue(account.status)} /></TableCell>
                  <TableCell align="right">
                    <Box sx={{ alignItems: 'center', display: 'flex', gap: 0.25, justifyContent: 'flex-end' }}>
                      <Tooltip title={account.can_manage ? messages.ai.verifyProvider : messages.ai.managedByPlatform}>
                        <span><Button size="small" startIcon={<CheckCircle2 size={15} />} disabled={busy || !account.can_manage} onClick={() => void testProvider(account.id)}>{messages.ai.test}</Button></span>
                      </Tooltip>
                      <Tooltip title={account.can_manage ? messages.ai.editProvider : messages.ai.managedByPlatform}>
                        <span><IconButton size="small" disabled={busy || !account.can_manage} onClick={() => openProviderEditor(account)} aria-label={format(messages.ai.editProviderAria, { name: account.name })}><Pencil size={16} /></IconButton></span>
                      </Tooltip>
                      <Tooltip title={account.can_manage ? messages.ai.deleteProvider : messages.ai.managedByPlatform}>
                        <span><IconButton size="small" color="error" disabled={busy || !account.can_manage} onClick={() => setProviderToDelete(account)} aria-label={format(messages.ai.deleteProviderAria, { name: account.name })}><Trash2 size={16} /></IconButton></span>
                      </Tooltip>
                    </Box>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      </Box>

      <Box component="section">
        <Box sx={{ alignItems: 'center', display: 'flex', justifyContent: 'space-between', mb: 1.5 }}>
          <Typography component="h2" variant="h2">{messages.ai.modelConfigurations}</Typography>
          <Button startIcon={<Plus size={16} />} onClick={() => setModelOpen(true)}>{messages.ai.addModel}</Button>
        </Box>
        <TableContainer component={Paper} variant="outlined">
          <Table>
            <TableHead><TableRow><TableCell>{messages.common.name}</TableCell><TableCell>{messages.ai.remoteModel}</TableCell><TableCell>{messages.ai.purpose}</TableCell><TableCell>{messages.ai.thinkingMode}</TableCell><TableCell>{messages.ai.dimension}</TableCell><TableCell>{messages.common.status}</TableCell><TableCell align="right">{messages.common.action}</TableCell></TableRow></TableHead>
            <TableBody>
              {models.map((model) => (
                <TableRow key={model.id} hover>
                  <TableCell><Typography fontWeight={650}>{model.name}</Typography></TableCell>
                  <TableCell>{model.model_name}</TableCell><TableCell>{labelValue(model.purpose)}</TableCell><TableCell>{model.purpose === 'chat' ? messages.ai[model.thinking_mode] : '—'}</TableCell><TableCell>{model.embedding_dimension ?? '—'}</TableCell>
                  <TableCell><Chip size="small" color={model.status === 'active' ? 'success' : 'default'} label={labelValue(model.status)} /></TableCell>
                  <TableCell align="right">{model.purpose === 'chat' && (model.status === 'active' ? <Button size="small" color="error" startIcon={<Power size={15} />} disabled={busy} onClick={() => void deactivate(model)}>{messages.ai.deactivate}</Button> : <Button size="small" startIcon={<Power size={15} />} disabled={busy} onClick={() => setActivateModel(model)}>{messages.ai.activate}</Button>)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      </Box>

      <Dialog open={providerOpen} onClose={() => setProviderOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{messages.ai.addProviderAccount}</DialogTitle>
        <DialogContent sx={{ display: 'grid', gap: 2, pt: '8px !important' }}>
          <TextField label={messages.common.name} value={providerName} onChange={(event) => setProviderName(event.target.value)} required />
          <FormControl><InputLabel>{messages.ai.providerKind}</InputLabel><Select label={messages.ai.providerKind} value={providerKind} onChange={(event) => setProviderKind(event.target.value as ProviderAccount['kind'])}><MenuItem value="fake">{messages.ai.fakeTestOnly}</MenuItem><MenuItem value="openai_compatible">{messages.ai.openAICompatible}</MenuItem></Select></FormControl>
          {providerKind === 'openai_compatible' && <><TextField label={messages.ai.baseUrl} value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} placeholder="https://api.example.com/v1" required /><TextField label={messages.ai.apiKey} type="password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} helperText={messages.ai.apiKeyHelp} required /></>}
        </DialogContent>
        <DialogActions><Button onClick={() => setProviderOpen(false)}>{messages.common.cancel}</Button><Button variant="contained" startIcon={<ServerCog size={16} />} disabled={!providerName.trim() || busy} onClick={() => void createProvider()}>{messages.ai.saveProvider}</Button></DialogActions>
      </Dialog>

      <Dialog open={modelOpen} onClose={() => setModelOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{messages.ai.addModelConfiguration}</DialogTitle>
        <DialogContent sx={{ display: 'grid', gap: 2, pt: '8px !important' }}>
          <FormControl><InputLabel>{messages.ai.provider}</InputLabel><Select label={messages.ai.provider} value={providerId} onChange={(event) => setProviderId(event.target.value)}>{accounts.filter((account) => account.status === 'ready').map((account) => <MenuItem key={account.id} value={account.id}>{account.name}</MenuItem>)}</Select></FormControl>
          <TextField label={messages.ai.configurationName} value={modelName} onChange={(event) => setModelName(event.target.value)} required />
          <TextField label={messages.ai.remoteModelName} value={remoteModelName} onChange={(event) => setRemoteModelName(event.target.value)} required />
          <FormControl><InputLabel>{messages.ai.purpose}</InputLabel><Select label={messages.ai.purpose} value={purpose} onChange={(event) => setPurpose(event.target.value as ModelConfig['purpose'])}><MenuItem value="chat">{messages.ai.chat}</MenuItem><MenuItem value="embedding">{messages.ai.embedding}</MenuItem></Select></FormControl>
          {purpose === 'chat' && <FormControl><InputLabel>{messages.ai.thinkingMode}</InputLabel><Select label={messages.ai.thinkingMode} value={thinkingMode} onChange={(event) => setThinkingMode(event.target.value as ModelConfig['thinking_mode'])}><MenuItem value="provider_default">{messages.ai.provider_default}</MenuItem><MenuItem value="disabled">{messages.ai.disabled}</MenuItem><MenuItem value="enabled">{messages.ai.enabled}</MenuItem></Select></FormControl>}
          {purpose === 'embedding' && <TextField label={messages.ai.embeddingDimension} type="number" value={dimension} onChange={(event) => setDimension(event.target.value)} inputProps={{ min: 8, max: 16384 }} />}
        </DialogContent>
        <DialogActions><Button onClick={() => setModelOpen(false)}>{messages.common.cancel}</Button><Button variant="contained" disabled={!providerId || !modelName.trim() || !remoteModelName.trim() || busy} onClick={() => void createModel()}>{messages.ai.saveModel}</Button></DialogActions>
      </Dialog>

      <Dialog open={editingProvider !== null} onClose={() => setEditingProvider(null)} fullWidth maxWidth="sm">
        <DialogTitle>{messages.ai.editProviderAccount}</DialogTitle>
        <DialogContent sx={{ display: 'grid', gap: 2, pt: '8px !important' }}>
          <TextField label={messages.common.name} value={editProviderName} onChange={(event) => setEditProviderName(event.target.value)} required />
          <TextField label={messages.ai.providerKind} value={editingProvider?.kind === 'fake' ? messages.ai.fakeTestOnly : messages.ai.openAICompatible} disabled />
          {editingProvider?.kind === 'openai_compatible' && <><TextField label={messages.ai.baseUrl} value={editBaseUrl} onChange={(event) => setEditBaseUrl(event.target.value)} placeholder="https://api.example.com/v1" helperText={messages.ai.apiRootHelp} required /><TextField label={messages.ai.replacementApiKey} type="password" value={replacementApiKey} onChange={(event) => setReplacementApiKey(event.target.value)} helperText={messages.ai.replacementApiKeyHelp} /></>}
        </DialogContent>
        <DialogActions><Button onClick={() => setEditingProvider(null)}>{messages.common.cancel}</Button><Button variant="contained" startIcon={<ServerCog size={16} />} disabled={!editProviderName.trim() || (editingProvider?.kind === 'openai_compatible' && !editBaseUrl.trim()) || busy} onClick={() => void updateProvider()}>{messages.ai.saveChanges}</Button></DialogActions>
      </Dialog>

      <Dialog open={providerToDelete !== null} onClose={() => setProviderToDelete(null)} fullWidth maxWidth="xs">
        <DialogTitle>{messages.ai.deleteProviderTitle}</DialogTitle>
        <DialogContent sx={{ pt: '8px !important' }}><Typography color="text.secondary">{format(messages.ai.deleteProviderDescription, { name: providerToDelete?.name ?? '' })}</Typography></DialogContent>
        <DialogActions><Button onClick={() => setProviderToDelete(null)}>{messages.common.cancel}</Button><Button color="error" variant="contained" startIcon={<Trash2 size={16} />} disabled={busy} onClick={() => void deleteProvider()}>{messages.ai.deleteProvider}</Button></DialogActions>
      </Dialog>

      <Dialog open={activateModel !== null} onClose={() => setActivateModel(null)} fullWidth maxWidth="xs">
        <DialogTitle>{messages.ai.activateChatModel}</DialogTitle>
        <DialogContent sx={{ pt: '8px !important' }}><FormControl fullWidth><InputLabel>{messages.common.application}</InputLabel><Select label={messages.common.application} value={applicationId} onChange={(event) => setApplicationId(event.target.value)}>{applications.filter((application) => application.status === 'active').map((application) => <MenuItem key={application.id} value={application.id}>{application.name}</MenuItem>)}</Select></FormControl></DialogContent>
        <DialogActions><Button onClick={() => setActivateModel(null)}>{messages.common.cancel}</Button><Button variant="contained" disabled={!applicationId || busy} onClick={() => void activate()}>{messages.ai.activate}</Button></DialogActions>
      </Dialog>
    </>
  );
};

export default AIPage;
