import { CssBaseline, LinearProgress, ThemeProvider } from '@mui/material';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RouterProvider } from '@tanstack/react-router';
import React, { Suspense } from 'react';
import { createRoot } from 'react-dom/client';

import { AuthProvider } from '@/auth/AuthProvider';
import { AppErrorBoundary } from '@/components/AppErrorBoundary';
import { I18nProvider, useI18n } from '@/i18n/I18nProvider';
import { router } from '@/router';
import { theme } from '@/theme';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, staleTime: 15_000 },
    mutations: { retry: false },
  },
});

const AdminApplication: React.FC = () => {
  const { messages } = useI18n();
  return (
    <AppErrorBoundary>
      <AuthProvider>
        <Suspense fallback={<LinearProgress aria-label={messages.app.loadingConsole} />}>
          <RouterProvider router={router} />
        </Suspense>
      </AuthProvider>
    </AppErrorBoundary>
  );
};

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <I18nProvider>
      <ThemeProvider theme={theme}>
        <CssBaseline />
        <QueryClientProvider client={queryClient}>
          <AdminApplication />
        </QueryClientProvider>
      </ThemeProvider>
    </I18nProvider>
  </React.StrictMode>,
);
