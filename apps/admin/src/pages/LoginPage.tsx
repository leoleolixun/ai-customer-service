import { Headphones } from 'lucide-react';
import { Alert, Box, Button, Paper, TextField, Typography } from '@mui/material';
import { useNavigate } from '@tanstack/react-router';
import React, { useCallback, useEffect, useRef, useState } from 'react';

import { errorMessage } from '@/api/client';
import { useAuth } from '@/auth/AuthProvider';

const LoginPage: React.FC = () => {
  const { user, checking, login } = useAuth();
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
      setError(errorMessage(cause));
    } finally {
      setSubmitting(false);
    }
  }, [email, login, navigate, password, tenantId]);

  return (
    <Box sx={{ alignItems: 'center', bgcolor: '#eef2f0', display: 'flex', justifyContent: 'center', minHeight: '100vh', p: 2 }}>
      <Paper component="form" onSubmit={(event) => void submit(event)} variant="outlined" sx={{ p: { xs: 3, sm: 4 }, width: 'min(420px, 100%)' }}>
        <Box sx={{ alignItems: 'center', display: 'flex', gap: 1.5, mb: 3 }}>
          <Box sx={{ alignItems: 'center', bgcolor: 'primary.light', borderRadius: 1, color: 'primary.dark', display: 'flex', height: 42, justifyContent: 'center', width: 42 }}>
            <Headphones size={22} />
          </Box>
          <Box>
            <Typography component="h1" fontSize={20} fontWeight={750}>Support Console</Typography>
            <Typography color="text.secondary" fontSize={13}>Secure staff access</Typography>
          </Box>
        </Box>
        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
        <Box sx={{ display: 'grid', gap: 2 }}>
          <TextField label="Email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} required autoComplete="username" />
          <TextField label="Password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} required autoComplete="current-password" />
          <TextField label="Tenant ID" value={tenantId} onChange={(event) => setTenantId(event.target.value)} helperText="Leave empty only for platform administrators" />
          <Button type="submit" variant="contained" size="large" disabled={submitting}>{submitting ? 'Signing in…' : 'Sign in'}</Button>
        </Box>
      </Paper>
    </Box>
  );
};

export default LoginPage;
