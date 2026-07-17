import { Headphones } from 'lucide-react';
import { Alert, Box, Button, Paper, TextField, Typography } from '@mui/material';
import { useNavigate } from '@tanstack/react-router';
import React, { useCallback, useEffect, useRef, useState } from 'react';

import { errorMessage } from '@/api/client';
import { useAuth } from '@/auth/AuthProvider';
import { useI18n } from '@/i18n/I18nProvider';
import LanguageMenu from '@/i18n/LanguageMenu';

const LoginPage: React.FC = () => {
  const { user, checking, login } = useAuth();
  const { messages } = useI18n();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [tenantId, setTenantId] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const redirecting = useRef(false);

  useEffect(() => {
    if (!checking && user && !redirecting.current) {
      redirecting.current = true;
      void navigate({ to: '/', replace: true });
    }
  }, [checking, navigate, user]);

  const submit = useCallback(async (event: React.FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await login({ email, password, tenantId });
      await navigate({ to: '/' });
    } catch (cause) {
      setError(errorMessage(cause, messages.common.requestFailed));
    } finally {
      setSubmitting(false);
    }
  }, [email, login, messages.common.requestFailed, navigate, password, tenantId]);

  return (
    <Box sx={{ alignItems: 'center', bgcolor: '#eef2f0', display: 'flex', justifyContent: 'center', minHeight: '100vh', p: 2, position: 'relative' }}>
      <Box sx={{ position: 'absolute', right: { xs: 12, sm: 24 }, top: { xs: 12, sm: 20 } }}>
        <LanguageMenu />
      </Box>
      <Paper component="form" onSubmit={(event) => void submit(event)} variant="outlined" sx={{ p: { xs: 3, sm: 4 }, width: 'min(420px, 100%)' }}>
        <Box sx={{ alignItems: 'center', display: 'flex', gap: 1.5, mb: 3 }}>
          <Box sx={{ alignItems: 'center', bgcolor: 'primary.light', borderRadius: 1, color: 'primary.dark', display: 'flex', height: 42, justifyContent: 'center', width: 42 }}>
            <Headphones size={22} />
          </Box>
          <Box>
            <Typography component="h1" fontSize={20} fontWeight={750}>{messages.app.name}</Typography>
            <Typography color="text.secondary" fontSize={13}>{messages.login.secureAccess}</Typography>
          </Box>
        </Box>
        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
        <Box sx={{ display: 'grid', gap: 2 }}>
          <TextField label={messages.common.email} type="email" value={email} onChange={(event) => setEmail(event.target.value)} required autoComplete="username" />
          <TextField label={messages.common.password} type="password" value={password} onChange={(event) => setPassword(event.target.value)} required autoComplete="current-password" />
          <TextField label={messages.login.tenantId} value={tenantId} onChange={(event) => setTenantId(event.target.value)} helperText={messages.login.tenantHelp} />
          <Button type="submit" variant="contained" size="large" disabled={submitting}>{submitting ? messages.login.signingIn : messages.login.signIn}</Button>
        </Box>
      </Paper>
    </Box>
  );
};

export default LoginPage;
