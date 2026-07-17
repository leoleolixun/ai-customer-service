import { AppWindow, CirclePause, FileUp, Link2, Plus, RefreshCw, Repeat2, RotateCcw, Search, Settings2, Trash2 } from 'lucide-react';
import {
  Alert,
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  FormControl,
  IconButton,
  InputLabel,
  List,
  ListItemButton,
  ListItemText,
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
import { useQuery, useQueryClient, useSuspenseQuery } from '@tanstack/react-query';
import React, { Suspense, useCallback, useState } from 'react';

import { api, ApiError, errorMessage } from '@/api/client';
import type {
  Application,
  KnowledgeBase,
  KnowledgeDocument,
  ModelConfig,
  SearchResult,
} from '@/api/types';
import PageHeader from '@/components/PageHeader';
import { useI18n } from '@/i18n/I18nProvider';

const KnowledgePage: React.FC = () => {
  const { labelValue, messages } = useI18n();
  const queryClient = useQueryClient();
  const { data: bases } = useSuspenseQuery({
    queryKey: ['knowledge-bases'],
    queryFn: () => api<KnowledgeBase[]>('/v1/admin/knowledge-bases'),
  });
  const { data: models } = useSuspenseQuery({
    queryKey: ['model-configs'],
    queryFn: () => api<ModelConfig[]>('/v1/admin/ai/model-configs'),
  });
  const [selectedId, setSelectedId] = useState<string | null>(bases[0]?.id ?? null);
  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [modelId, setModelId] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const create = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const created = await api<KnowledgeBase>('/v1/admin/knowledge-bases', {
        method: 'POST',
        body: JSON.stringify({ name, description, embedding_model_config_id: modelId }),
      });
      await queryClient.invalidateQueries({ queryKey: ['knowledge-bases'] });
      setSelectedId(created.id);
      setOpen(false);
      setName('');
      setDescription('');
    } catch (cause) {
      setError(errorMessage(cause, messages.common.requestFailed));
    } finally {
      setBusy(false);
    }
  }, [description, messages.common.requestFailed, modelId, name, queryClient]);

  const selected = bases.find((item) => item.id === selectedId) ?? null;
  return (
    <>
      <PageHeader title={messages.knowledge.title} description={messages.knowledge.description} action={{ label: messages.knowledge.newKnowledgeBase, icon: Plus, onClick: () => setOpen(true) }} />
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', lg: '260px minmax(0, 1fr)' }, minHeight: 560 }}>
        <Paper variant="outlined" sx={{ alignSelf: 'start', overflow: 'hidden' }}>
          <Typography fontSize={12} fontWeight={700} sx={{ px: 2, py: 1.5 }} textTransform="uppercase">{messages.knowledge.knowledgeBases}</Typography>
          <Divider />
          <List disablePadding>
            {bases.map((base) => (
              <ListItemButton key={base.id} selected={base.id === selectedId} onClick={() => setSelectedId(base.id)}>
                <ListItemText primary={base.name} secondary={`${base.embedding_model_name} · ${labelValue(base.status)}`} primaryTypographyProps={{ fontSize: 14, fontWeight: 650 }} secondaryTypographyProps={{ fontSize: 11 }} />
              </ListItemButton>
            ))}
          </List>
        </Paper>
        <Paper variant="outlined" sx={{ minWidth: 0, p: { xs: 2, md: 3 } }}>
          {selected ? (
            <Suspense fallback={<Typography color="text.secondary">{messages.knowledge.loadingDocuments}</Typography>}>
              <KnowledgeDetail base={selected} />
            </Suspense>
          ) : (
            <Typography color="text.secondary">{messages.knowledge.createFirst}</Typography>
          )}
        </Paper>
      </Box>

      <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{messages.knowledge.newKnowledgeBase}</DialogTitle>
        <DialogContent sx={{ display: 'grid', gap: 2, pt: '8px !important' }}>
          <TextField label={messages.common.name} value={name} onChange={(event) => setName(event.target.value)} required />
          <TextField label={messages.common.description} value={description} onChange={(event) => setDescription(event.target.value)} multiline minRows={2} />
          <FormControl><InputLabel>{messages.knowledge.embeddingModel}</InputLabel><Select label={messages.knowledge.embeddingModel} value={modelId} onChange={(event) => setModelId(event.target.value)}>{models.filter((model) => model.purpose === 'embedding').map((model) => <MenuItem key={model.id} value={model.id}>{model.name} ({model.embedding_dimension})</MenuItem>)}</Select></FormControl>
        </DialogContent>
        <DialogActions><Button onClick={() => setOpen(false)}>{messages.common.cancel}</Button><Button variant="contained" disabled={!name.trim() || !modelId || busy} onClick={() => void create()}>{messages.common.create}</Button></DialogActions>
      </Dialog>
    </>
  );
};

const KnowledgeDetail: React.FC<{ base: KnowledgeBase }> = ({ base }) => {
  const { format, labelValue, language, messages } = useI18n();
  const queryClient = useQueryClient();
  const { data: documents = [], error: documentsError } = useQuery({
    queryKey: ['knowledge-documents', base.id],
    queryFn: () => api<KnowledgeDocument[]>(`/v1/admin/knowledge-bases/${base.id}/documents`),
    refetchInterval: (query) => query.state.data?.some((item) => ['uploaded', 'processing'].includes(item.status)) ? 2000 : false,
  });
  const { data: applications } = useSuspenseQuery({
    queryKey: ['applications'],
    queryFn: () => api<Application[]>('/v1/admin/applications'),
  });
  const { data: boundApplications = [], error: boundApplicationsError } = useQuery({
    queryKey: ['knowledge-base-applications', base.id],
    queryFn: () => api<Application[]>(`/v1/admin/knowledge-bases/${base.id}/applications`),
  });
  const [uploadOpen, setUploadOpen] = useState(false);
  const [bindOpen, setBindOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [keywordThreshold, setKeywordThreshold] = useState(String(base.keyword_score_threshold));
  const [vectorThreshold, setVectorThreshold] = useState(String(base.vector_similarity_threshold));
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState('');
  const [sourceUrl, setSourceUrl] = useState('');
  const [replacement, setReplacement] = useState<KnowledgeDocument | null>(null);
  const [deleting, setDeleting] = useState<KnowledgeDocument | null>(null);
  const [applicationId, setApplicationId] = useState('');
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const upload = useCallback(async () => {
    if (!file) return;
    setBusy(true);
    setError(null);
    const form = new FormData();
    form.set('file', file);
    form.set('title', title || file.name);
    if (sourceUrl) form.set('source_url', sourceUrl);
    if (replacement) form.set('replace_document_id', replacement.id);
    try {
      await api(`/v1/admin/knowledge-bases/${base.id}/documents`, { method: 'POST', body: form });
      setUploadOpen(false);
      setFile(null);
      setTitle('');
      setSourceUrl('');
      setReplacement(null);
      await queryClient.invalidateQueries({ queryKey: ['knowledge-documents', base.id] });
    } catch (cause) {
      setError(errorMessage(cause, messages.common.requestFailed));
    } finally {
      setBusy(false);
    }
  }, [base.id, file, messages.common.requestFailed, queryClient, replacement, sourceUrl, title]);

  const openUpload = useCallback((document: KnowledgeDocument | null = null) => {
    setReplacement(document);
    setFile(null);
    setTitle(document?.title ?? '');
    setSourceUrl(document?.source_url ?? '');
    setUploadOpen(true);
  }, []);

  const retry = useCallback(async (document: KnowledgeDocument) => {
    setBusy(true);
    setError(null);
    try {
      await api(`/v1/admin/knowledge-bases/${base.id}/documents/${document.id}/retry`, { method: 'POST' });
      await queryClient.invalidateQueries({ queryKey: ['knowledge-documents', base.id] });
    } catch (cause) {
      setError(errorMessage(cause, messages.common.requestFailed));
    } finally {
      setBusy(false);
    }
  }, [base.id, messages.common.requestFailed, queryClient]);

  const updateDocumentStatus = useCallback(async (document: KnowledgeDocument) => {
    const status = document.status === 'ready' ? 'disabled' : 'ready';
    setBusy(true);
    setError(null);
    try {
      await api(`/v1/admin/knowledge-bases/${base.id}/documents/${document.id}/status`, {
        method: 'PATCH',
        body: JSON.stringify({ status }),
      });
      setResults([]);
      await queryClient.invalidateQueries({ queryKey: ['knowledge-documents', base.id] });
    } catch (cause) {
      setError(errorMessage(cause, messages.common.requestFailed));
    } finally {
      setBusy(false);
    }
  }, [base.id, messages.common.requestFailed, queryClient]);

  const deleteDocument = useCallback(async () => {
    if (!deleting) return;
    setBusy(true);
    setError(null);
    try {
      await api(`/v1/admin/knowledge-bases/${base.id}/documents/${deleting.id}`, { method: 'DELETE' });
      setDeleting(null);
      await queryClient.invalidateQueries({ queryKey: ['knowledge-documents', base.id] });
    } catch (cause) {
      setError(errorMessage(cause, messages.common.requestFailed));
      if (cause instanceof ApiError && cause.code === 'object_storage_delete_failed') {
        setDeleting(null);
      }
      await queryClient.invalidateQueries({ queryKey: ['knowledge-documents', base.id] });
    } finally {
      setBusy(false);
    }
  }, [base.id, deleting, messages.common.requestFailed, queryClient]);

  const bind = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      await api(`/v1/admin/knowledge-bases/${base.id}/applications/${applicationId}`, { method: 'PUT' });
      await queryClient.invalidateQueries({ queryKey: ['knowledge-base-applications', base.id] });
      setBindOpen(false);
      setApplicationId('');
    } catch (cause) {
      setError(errorMessage(cause, messages.common.requestFailed));
    } finally {
      setBusy(false);
    }
  }, [applicationId, base.id, messages.common.requestFailed, queryClient]);

  const unbind = useCallback(async (id: string) => {
    setBusy(true);
    setError(null);
    try {
      await api(`/v1/admin/knowledge-bases/${base.id}/applications/${id}`, { method: 'DELETE' });
      await queryClient.invalidateQueries({ queryKey: ['knowledge-base-applications', base.id] });
    } catch (cause) {
      setError(errorMessage(cause, messages.common.requestFailed));
    } finally {
      setBusy(false);
    }
  }, [base.id, messages.common.requestFailed, queryClient]);

  const search = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      setResults(await api<SearchResult[]>(`/v1/admin/knowledge-bases/${base.id}/search`, { method: 'POST', body: JSON.stringify({ query, top_k: 5 }) }));
    } catch (cause) {
      setError(errorMessage(cause, messages.common.requestFailed));
    } finally {
      setBusy(false);
    }
  }, [base.id, messages.common.requestFailed, query]);

  const openSettings = useCallback(() => {
    setKeywordThreshold(String(base.keyword_score_threshold));
    setVectorThreshold(String(base.vector_similarity_threshold));
    setSettingsOpen(true);
  }, [base.keyword_score_threshold, base.vector_similarity_threshold]);

  const saveSettings = useCallback(async () => {
    const keyword = Number(keywordThreshold);
    const vector = Number(vectorThreshold);
    if (![keyword, vector].every((value) => Number.isFinite(value) && value >= 0 && value <= 1)) return;
    setBusy(true);
    setError(null);
    try {
      await api(`/v1/admin/knowledge-bases/${base.id}`, {
        method: 'PATCH',
        body: JSON.stringify({
          keyword_score_threshold: keyword,
          vector_similarity_threshold: vector,
        }),
      });
      await queryClient.invalidateQueries({ queryKey: ['knowledge-bases'] });
      setSettingsOpen(false);
    } catch (cause) {
      setError(errorMessage(cause, messages.common.requestFailed));
    } finally {
      setBusy(false);
    }
  }, [base.id, keywordThreshold, messages.common.requestFailed, queryClient, vectorThreshold]);

  const thresholdsValid = [Number(keywordThreshold), Number(vectorThreshold)]
    .every((value) => Number.isFinite(value) && value >= 0 && value <= 1);

  return (
    <>
      <Box sx={{ alignItems: { sm: 'center' }, display: 'flex', flexDirection: { xs: 'column', sm: 'row' }, gap: 1.5, justifyContent: 'space-between', mb: 2 }}>
        <Box>
          <Typography component="h2" variant="h2">{base.name}</Typography>
          <Typography color="text.secondary" fontSize={12}>
            {base.description || format(messages.knowledge.dimensions, {
              model: base.embedding_model_name,
              dimensions: base.embedding_dimension,
            })}
          </Typography>
          <Typography color="text.secondary" fontSize={11}>
            {format(messages.knowledge.retrievalThresholds, {
              keyword: base.keyword_score_threshold.toFixed(2),
              vector: base.vector_similarity_threshold.toFixed(2),
            })}
          </Typography>
        </Box>
        <Box sx={{ display: 'flex', gap: 1 }}>
          <Tooltip title={messages.knowledge.retrievalSettings}>
            <IconButton aria-label={messages.knowledge.retrievalSettings} onClick={openSettings}>
              <Settings2 size={17} />
            </IconButton>
          </Tooltip>
          <Button startIcon={<Link2 size={15} />} disabled={Boolean(boundApplicationsError) || boundApplications.length === applications.length} onClick={() => setBindOpen(true)}>{messages.knowledge.bindApp}</Button>
          <Button variant="contained" startIcon={<FileUp size={15} />} disabled={Boolean(documentsError)} onClick={() => openUpload()}>{messages.knowledge.upload}</Button>
        </Box>
      </Box>
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
      {documentsError && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {errorMessage(documentsError, messages.knowledge.documentsLoadFailed)}
        </Alert>
      )}
      {boundApplicationsError && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {errorMessage(boundApplicationsError, messages.knowledge.bindingsLoadFailed)}
        </Alert>
      )}
      <Box sx={{ alignItems: 'center', display: 'flex', flexWrap: 'wrap', gap: 1, mb: 2 }}>
        <Typography color="text.secondary" fontSize={12}>{messages.knowledge.boundApplications}</Typography>
        {boundApplications.map((application) => <Chip key={application.id} label={application.name} size="small" disabled={busy || Boolean(boundApplicationsError)} onDelete={() => void unbind(application.id)} />)}
        {!boundApplicationsError && boundApplications.length === 0 && <Typography color="text.secondary" fontSize={12}>{messages.common.none}</Typography>}
      </Box>
      <TableContainer sx={{ border: 1, borderColor: 'divider', borderRadius: 1 }}>
        <Table size="small">
          <TableHead><TableRow><TableCell>{messages.knowledge.document}</TableCell><TableCell>{messages.knowledge.version}</TableCell><TableCell>{messages.knowledge.size}</TableCell><TableCell>{messages.common.status}</TableCell><TableCell>{messages.common.updated}</TableCell><TableCell align="right">{messages.common.actions}</TableCell></TableRow></TableHead>
          <TableBody>
            {documents.map((document) => {
              const processing = ['uploaded', 'processing'].includes(document.status);
              const restoreAllowed = document.can_restore;
              const restoreTooltip = restoreAllowed
                ? messages.knowledge.restoreDocument
                : document.restore_block_reason === 'document_restore_base_disabled'
                  ? messages.knowledge.restoreBlockedByBase
                  : messages.knowledge.restoreBlockedByVersion;
              return (
                <TableRow key={document.id}>
                  <TableCell><Typography fontSize={13} fontWeight={650}>{document.title}</Typography><Typography color="text.secondary" fontSize={11}>{document.source_filename}</Typography>{document.status === 'failed' && <Typography color="error.main" fontSize={11}>{messages.knowledge.ingestionFailed}</Typography>}</TableCell>
                  <TableCell>{format(messages.knowledge.documentVersion, { version: document.version })}</TableCell>
                  <TableCell>{format(messages.knowledge.documentSize, { size: Math.ceil(document.byte_size / 1024) })}</TableCell>
                  <TableCell><Chip size="small" color={document.status === 'ready' ? 'success' : document.status === 'failed' ? 'error' : 'default'} label={labelValue(document.status)} /></TableCell>
                  <TableCell>{new Date(document.updated_at).toLocaleString(language)}</TableCell>
                  <TableCell align="right" sx={{ whiteSpace: 'nowrap', width: 144 }}>
                    <Tooltip title={messages.knowledge.uploadReplacement}><span><IconButton size="small" disabled={processing || busy || Boolean(documentsError)} aria-label={format(messages.knowledge.replaceAria, { name: document.title })} onClick={() => openUpload(document)}><Repeat2 size={15} /></IconButton></span></Tooltip>
                    {document.status === 'failed' && <Tooltip title={messages.knowledge.retryIngestion}><span><IconButton size="small" disabled={busy || Boolean(documentsError)} aria-label={format(messages.knowledge.retryAria, { name: document.title })} onClick={() => void retry(document)}><RefreshCw size={15} /></IconButton></span></Tooltip>}
                    {document.status === 'ready' && <Tooltip title={messages.knowledge.disableDocument}><span><IconButton size="small" disabled={busy || Boolean(documentsError)} aria-label={format(messages.knowledge.disableAria, { name: document.title })} onClick={() => void updateDocumentStatus(document)}><CirclePause size={15} /></IconButton></span></Tooltip>}
                    {document.status === 'disabled' && <Tooltip title={restoreTooltip}><span><IconButton size="small" disabled={busy || Boolean(documentsError) || !restoreAllowed} aria-label={format(messages.knowledge.restoreAria, { name: document.title })} onClick={() => void updateDocumentStatus(document)}><RotateCcw size={15} /></IconButton></span></Tooltip>}
                    <Tooltip title={messages.knowledge.deleteDocument}><span><IconButton size="small" color="error" disabled={processing || busy || Boolean(documentsError)} aria-label={format(messages.knowledge.deleteAria, { name: document.title })} onClick={() => setDeleting(document)}><Trash2 size={15} /></IconButton></span></Tooltip>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </TableContainer>

      <Divider sx={{ my: 3 }} />
      <Typography component="h2" variant="h2" sx={{ mb: 1.5 }}>{messages.knowledge.retrievalDiagnostics}</Typography>
      <Box sx={{ display: 'grid', gap: 1, gridTemplateColumns: 'minmax(0, 1fr) auto' }}><TextField size="small" value={query} onChange={(event) => setQuery(event.target.value)} placeholder={messages.knowledge.searchPlaceholder} /><Button variant="outlined" startIcon={<Search size={15} />} disabled={!query.trim() || busy} onClick={() => void search()}>{messages.knowledge.search}</Button></Box>
      <Box sx={{ display: 'grid', gap: 1, mt: 2 }}>{results.map((result) => <Box key={result.chunk_id} sx={{ borderBottom: 1, borderColor: 'divider', pb: 1.5 }}><Typography fontSize={13} fontWeight={650}>{result.document_title}</Typography><Typography color="text.secondary" fontSize={12} sx={{ my: 0.5 }}>{result.content}</Typography><Typography color="primary.main" fontSize={11}>{format(messages.knowledge.resultScores, { rrf: result.score.toFixed(4), vector: result.vector_similarity.toFixed(3), keyword: result.keyword_score.toFixed(3) })}</Typography></Box>)}</Box>

      <Dialog open={uploadOpen} onClose={() => setUploadOpen(false)} fullWidth maxWidth="sm"><DialogTitle>{replacement ? format(messages.knowledge.replaceTitle, { name: replacement.title }) : messages.knowledge.uploadDocument}</DialogTitle><DialogContent sx={{ display: 'grid', gap: 2, pt: '8px !important' }}>{replacement && <Alert severity="info">{messages.knowledge.replacementInfo}</Alert>}<Button component="label" variant="outlined" startIcon={<FileUp size={16} />}>{file?.name ?? messages.knowledge.chooseFile}<input hidden type="file" accept=".txt,.md,.pdf,text/plain,text/markdown,application/pdf" onChange={(event) => setFile(event.target.files?.[0] ?? null)} /></Button><TextField label={messages.knowledge.documentTitle} value={title} onChange={(event) => setTitle(event.target.value)} /><TextField label={messages.knowledge.sourceUrl} value={sourceUrl} onChange={(event) => setSourceUrl(event.target.value)} /></DialogContent><DialogActions><Button onClick={() => setUploadOpen(false)}>{messages.common.cancel}</Button><Button variant="contained" disabled={!file || busy} onClick={() => void upload()}>{replacement ? messages.knowledge.uploadReplacement : messages.knowledge.upload}</Button></DialogActions></Dialog>
      <Dialog open={bindOpen} onClose={() => setBindOpen(false)} fullWidth maxWidth="xs"><DialogTitle>{messages.knowledge.bindToApplication}</DialogTitle><DialogContent sx={{ pt: '8px !important' }}><FormControl fullWidth><InputLabel>{messages.common.application}</InputLabel><Select label={messages.common.application} value={applicationId} onChange={(event) => setApplicationId(event.target.value)}>{applications.filter((application) => !boundApplications.some((bound) => bound.id === application.id)).map((application) => <MenuItem key={application.id} value={application.id}><Box sx={{ alignItems: 'center', display: 'flex', gap: 1 }}><AppWindow size={15} />{application.name}</Box></MenuItem>)}</Select></FormControl></DialogContent><DialogActions><Button onClick={() => setBindOpen(false)}>{messages.common.cancel}</Button><Button variant="contained" disabled={!applicationId || busy} onClick={() => void bind()}>{messages.knowledge.bind}</Button></DialogActions></Dialog>
      <Dialog open={settingsOpen} onClose={() => !busy && setSettingsOpen(false)} fullWidth maxWidth="xs">
        <DialogTitle>{messages.knowledge.retrievalSettings}</DialogTitle>
        <DialogContent sx={{ display: 'grid', gap: 2, pt: '8px !important' }}>
          <TextField type="number" label={messages.knowledge.keywordThreshold} value={keywordThreshold} onChange={(event) => setKeywordThreshold(event.target.value)} inputProps={{ min: 0, max: 1, step: 0.01 }} />
          <TextField type="number" label={messages.knowledge.vectorThreshold} value={vectorThreshold} onChange={(event) => setVectorThreshold(event.target.value)} inputProps={{ min: 0, max: 1, step: 0.01 }} />
          <Typography color="text.secondary" fontSize={12}>{messages.knowledge.thresholdHelp}</Typography>
        </DialogContent>
        <DialogActions>
          <Button disabled={busy} onClick={() => setSettingsOpen(false)}>{messages.common.cancel}</Button>
          <Button variant="contained" disabled={busy || !thresholdsValid} onClick={() => void saveSettings()}>{messages.knowledge.saveRetrievalSettings}</Button>
        </DialogActions>
      </Dialog>
      <Dialog open={Boolean(deleting)} onClose={() => !busy && setDeleting(null)} fullWidth maxWidth="xs"><DialogTitle>{messages.knowledge.deleteDocumentTitle}</DialogTitle><DialogContent><Typography color="text.secondary" fontSize={13}>{format(messages.knowledge.deleteDocumentDescription, { name: deleting?.title ?? '' })}</Typography></DialogContent><DialogActions><Button onClick={() => setDeleting(null)} disabled={busy}>{messages.common.cancel}</Button><Button color="error" variant="contained" disabled={busy} onClick={() => void deleteDocument()}>{messages.common.delete}</Button></DialogActions></Dialog>
    </>
  );
};

export default KnowledgePage;
