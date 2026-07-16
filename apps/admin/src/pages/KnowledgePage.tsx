import { AppWindow, FileUp, Link2, Plus, RefreshCw, Repeat2, Search, Trash2 } from 'lucide-react';
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

import { api, errorMessage } from '@/api/client';
import type {
  Application,
  KnowledgeBase,
  KnowledgeDocument,
  ModelConfig,
  SearchResult,
} from '@/api/types';
import PageHeader from '@/components/PageHeader';

const KnowledgePage: React.FC = () => {
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
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }, [description, modelId, name, queryClient]);

  const selected = bases.find((item) => item.id === selectedId) ?? null;
  return (
    <>
      <PageHeader title="Knowledge" description="Versioned source documents and retrieval diagnostics." action={{ label: 'New knowledge base', icon: Plus, onClick: () => setOpen(true) }} />
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', lg: '260px minmax(0, 1fr)' }, minHeight: 560 }}>
        <Paper variant="outlined" sx={{ alignSelf: 'start', overflow: 'hidden' }}>
          <Typography fontSize={12} fontWeight={700} sx={{ px: 2, py: 1.5 }} textTransform="uppercase">Knowledge bases</Typography>
          <Divider />
          <List disablePadding>
            {bases.map((base) => (
              <ListItemButton key={base.id} selected={base.id === selectedId} onClick={() => setSelectedId(base.id)}>
                <ListItemText primary={base.name} secondary={`${base.embedding_model_name} · ${base.status}`} primaryTypographyProps={{ fontSize: 14, fontWeight: 650 }} secondaryTypographyProps={{ fontSize: 11 }} />
              </ListItemButton>
            ))}
          </List>
        </Paper>
        <Paper variant="outlined" sx={{ minWidth: 0, p: { xs: 2, md: 3 } }}>
          {selected ? (
            <Suspense fallback={<Typography color="text.secondary">Loading documents…</Typography>}>
              <KnowledgeDetail base={selected} />
            </Suspense>
          ) : (
            <Typography color="text.secondary">Create a knowledge base to add source documents.</Typography>
          )}
        </Paper>
      </Box>

      <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>New knowledge base</DialogTitle>
        <DialogContent sx={{ display: 'grid', gap: 2, pt: '8px !important' }}>
          <TextField label="Name" value={name} onChange={(event) => setName(event.target.value)} required />
          <TextField label="Description" value={description} onChange={(event) => setDescription(event.target.value)} multiline minRows={2} />
          <FormControl><InputLabel>Embedding model</InputLabel><Select label="Embedding model" value={modelId} onChange={(event) => setModelId(event.target.value)}>{models.filter((model) => model.purpose === 'embedding').map((model) => <MenuItem key={model.id} value={model.id}>{model.name} ({model.embedding_dimension})</MenuItem>)}</Select></FormControl>
        </DialogContent>
        <DialogActions><Button onClick={() => setOpen(false)}>Cancel</Button><Button variant="contained" disabled={!name.trim() || !modelId || busy} onClick={() => void create()}>Create</Button></DialogActions>
      </Dialog>
    </>
  );
};

const KnowledgeDetail: React.FC<{ base: KnowledgeBase }> = ({ base }) => {
  const queryClient = useQueryClient();
  const { data: documents = [] } = useQuery({
    queryKey: ['knowledge-documents', base.id],
    queryFn: () => api<KnowledgeDocument[]>(`/v1/admin/knowledge-bases/${base.id}/documents`),
    refetchInterval: (query) => query.state.data?.some((item) => ['uploaded', 'processing'].includes(item.status)) ? 2000 : false,
  });
  const { data: applications } = useSuspenseQuery({
    queryKey: ['applications'],
    queryFn: () => api<Application[]>('/v1/admin/applications'),
  });
  const { data: boundApplications = [] } = useQuery({
    queryKey: ['knowledge-base-applications', base.id],
    queryFn: () => api<Application[]>(`/v1/admin/knowledge-bases/${base.id}/applications`),
  });
  const [uploadOpen, setUploadOpen] = useState(false);
  const [bindOpen, setBindOpen] = useState(false);
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
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }, [base.id, file, queryClient, replacement, sourceUrl, title]);

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
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }, [base.id, queryClient]);

  const deleteDocument = useCallback(async () => {
    if (!deleting) return;
    setBusy(true);
    setError(null);
    try {
      await api(`/v1/admin/knowledge-bases/${base.id}/documents/${deleting.id}`, { method: 'DELETE' });
      setDeleting(null);
      await queryClient.invalidateQueries({ queryKey: ['knowledge-documents', base.id] });
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }, [base.id, deleting, queryClient]);

  const bind = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      await api(`/v1/admin/knowledge-bases/${base.id}/applications/${applicationId}`, { method: 'PUT' });
      await queryClient.invalidateQueries({ queryKey: ['knowledge-base-applications', base.id] });
      setBindOpen(false);
      setApplicationId('');
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }, [applicationId, base.id, queryClient]);

  const unbind = useCallback(async (id: string) => {
    setBusy(true);
    setError(null);
    try {
      await api(`/v1/admin/knowledge-bases/${base.id}/applications/${id}`, { method: 'DELETE' });
      await queryClient.invalidateQueries({ queryKey: ['knowledge-base-applications', base.id] });
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }, [base.id, queryClient]);

  const search = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      setResults(await api<SearchResult[]>(`/v1/admin/knowledge-bases/${base.id}/search`, { method: 'POST', body: JSON.stringify({ query, top_k: 5 }) }));
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }, [base.id, query]);

  return (
    <>
      <Box sx={{ alignItems: { sm: 'center' }, display: 'flex', flexDirection: { xs: 'column', sm: 'row' }, gap: 1.5, justifyContent: 'space-between', mb: 2 }}>
        <Box><Typography component="h2" variant="h2">{base.name}</Typography><Typography color="text.secondary" fontSize={12}>{base.description || `${base.embedding_model_name} · ${base.embedding_dimension} dimensions`}</Typography></Box>
        <Box sx={{ display: 'flex', gap: 1 }}><Button startIcon={<Link2 size={15} />} disabled={boundApplications.length === applications.length} onClick={() => setBindOpen(true)}>Bind app</Button><Button variant="contained" startIcon={<FileUp size={15} />} onClick={() => openUpload()}>Upload</Button></Box>
      </Box>
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
      <Box sx={{ alignItems: 'center', display: 'flex', flexWrap: 'wrap', gap: 1, mb: 2 }}>
        <Typography color="text.secondary" fontSize={12}>Bound applications</Typography>
        {boundApplications.map((application) => <Chip key={application.id} label={application.name} size="small" disabled={busy} onDelete={() => void unbind(application.id)} />)}
        {boundApplications.length === 0 && <Typography color="text.secondary" fontSize={12}>None</Typography>}
      </Box>
      <TableContainer sx={{ border: 1, borderColor: 'divider', borderRadius: 1 }}>
        <Table size="small"><TableHead><TableRow><TableCell>Document</TableCell><TableCell>Version</TableCell><TableCell>Size</TableCell><TableCell>Status</TableCell><TableCell>Updated</TableCell><TableCell align="right">Actions</TableCell></TableRow></TableHead><TableBody>{documents.map((document) => { const processing = ['uploaded', 'processing'].includes(document.status); return <TableRow key={document.id}><TableCell><Typography fontSize={13} fontWeight={650}>{document.title}</Typography><Typography color="text.secondary" fontSize={11}>{document.source_filename}</Typography>{document.error_message && <Typography color="error.main" fontSize={11}>{document.error_message}</Typography>}</TableCell><TableCell>v{document.version}</TableCell><TableCell>{Math.ceil(document.byte_size / 1024)} KB</TableCell><TableCell><Chip size="small" color={document.status === 'ready' ? 'success' : document.status === 'failed' ? 'error' : 'default'} label={document.status} /></TableCell><TableCell>{new Date(document.updated_at).toLocaleString()}</TableCell><TableCell align="right" sx={{ whiteSpace: 'nowrap', width: 112 }}><Tooltip title="Upload replacement"><span><IconButton size="small" disabled={processing || busy} aria-label={`Replace ${document.title}`} onClick={() => openUpload(document)}><Repeat2 size={15} /></IconButton></span></Tooltip>{document.status === 'failed' && <Tooltip title="Retry ingestion"><span><IconButton size="small" disabled={busy} aria-label={`Retry ${document.title}`} onClick={() => void retry(document)}><RefreshCw size={15} /></IconButton></span></Tooltip>}<Tooltip title="Delete document"><span><IconButton size="small" color="error" disabled={processing || busy} aria-label={`Delete ${document.title}`} onClick={() => setDeleting(document)}><Trash2 size={15} /></IconButton></span></Tooltip></TableCell></TableRow>; })}</TableBody></Table>
      </TableContainer>

      <Divider sx={{ my: 3 }} />
      <Typography component="h2" variant="h2" sx={{ mb: 1.5 }}>Retrieval diagnostics</Typography>
      <Box sx={{ display: 'grid', gap: 1, gridTemplateColumns: 'minmax(0, 1fr) auto' }}><TextField size="small" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search this knowledge base" /><Button variant="outlined" startIcon={<Search size={15} />} disabled={!query.trim() || busy} onClick={() => void search()}>Search</Button></Box>
      <Box sx={{ display: 'grid', gap: 1, mt: 2 }}>{results.map((result) => <Box key={result.chunk_id} sx={{ borderBottom: 1, borderColor: 'divider', pb: 1.5 }}><Typography fontSize={13} fontWeight={650}>{result.document_title}</Typography><Typography color="text.secondary" fontSize={12} sx={{ my: 0.5 }}>{result.content}</Typography><Typography color="primary.main" fontSize={11}>RRF {result.score.toFixed(4)} · vector {result.vector_similarity.toFixed(3)} · keyword {result.keyword_score.toFixed(3)}</Typography></Box>)}</Box>

      <Dialog open={uploadOpen} onClose={() => setUploadOpen(false)} fullWidth maxWidth="sm"><DialogTitle>{replacement ? `Replace ${replacement.title}` : 'Upload document'}</DialogTitle><DialogContent sx={{ display: 'grid', gap: 2, pt: '8px !important' }}>{replacement && <Alert severity="info">The existing version remains active until the replacement finishes processing.</Alert>}<Button component="label" variant="outlined" startIcon={<FileUp size={16} />}>{file?.name ?? 'Choose TXT, Markdown, or PDF'}<input hidden type="file" accept=".txt,.md,.pdf,text/plain,text/markdown,application/pdf" onChange={(event) => setFile(event.target.files?.[0] ?? null)} /></Button><TextField label="Title" value={title} onChange={(event) => setTitle(event.target.value)} /><TextField label="Source URL" value={sourceUrl} onChange={(event) => setSourceUrl(event.target.value)} /></DialogContent><DialogActions><Button onClick={() => setUploadOpen(false)}>Cancel</Button><Button variant="contained" disabled={!file || busy} onClick={() => void upload()}>{replacement ? 'Upload replacement' : 'Upload'}</Button></DialogActions></Dialog>
      <Dialog open={bindOpen} onClose={() => setBindOpen(false)} fullWidth maxWidth="xs"><DialogTitle>Bind to application</DialogTitle><DialogContent sx={{ pt: '8px !important' }}><FormControl fullWidth><InputLabel>Application</InputLabel><Select label="Application" value={applicationId} onChange={(event) => setApplicationId(event.target.value)}>{applications.filter((application) => !boundApplications.some((bound) => bound.id === application.id)).map((application) => <MenuItem key={application.id} value={application.id}><Box sx={{ alignItems: 'center', display: 'flex', gap: 1 }}><AppWindow size={15} />{application.name}</Box></MenuItem>)}</Select></FormControl></DialogContent><DialogActions><Button onClick={() => setBindOpen(false)}>Cancel</Button><Button variant="contained" disabled={!applicationId || busy} onClick={() => void bind()}>Bind</Button></DialogActions></Dialog>
      <Dialog open={Boolean(deleting)} onClose={() => !busy && setDeleting(null)} fullWidth maxWidth="xs"><DialogTitle>Delete document?</DialogTitle><DialogContent><Typography color="text.secondary" fontSize={13}>This removes {deleting?.title} from retrieval and deletes its stored source file. This action cannot be undone.</Typography></DialogContent><DialogActions><Button onClick={() => setDeleting(null)} disabled={busy}>Cancel</Button><Button color="error" variant="contained" disabled={busy} onClick={() => void deleteDocument()}>Delete</Button></DialogActions></Dialog>
    </>
  );
};

export default KnowledgePage;
