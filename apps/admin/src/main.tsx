import { CssBaseline, LinearProgress, ThemeProvider } from '@mui/material';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RouterProvider } from '@tanstack/react-router';
import React, { Suspense } from 'react';
import { createRoot } from 'react-dom/client';

import { AuthProvider } from '@/auth/AuthProvider';
import { AppErrorBoundary } from '@/components/AppErrorBoundary';
import { router } from '@/router';
import { theme } from '@/theme';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, staleTime: 15_000 },
    mutations: { retry: false },
  },
});

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <QueryClientProvider client={queryClient}>
        <AppErrorBoundary>
          <AuthProvider>
            <Suspense fallback={<LinearProgress aria-label="Loading console" />}>
              <RouterProvider router={router} />
            </Suspense>
          </AuthProvider>
        </AppErrorBoundary>
      </QueryClientProvider>
    </ThemeProvider>
  </React.StrictMode>,
);
