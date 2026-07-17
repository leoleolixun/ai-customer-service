import { AlertTriangle, RotateCcw } from 'lucide-react';
import { Box, Button, Paper, Typography } from '@mui/material';
import React from 'react';

import { useI18n } from '@/i18n/I18nProvider';
import type { Messages } from '@/i18n/messages';

interface State {
  error: Error | null;
}

interface BoundaryProps extends React.PropsWithChildren {
  messages: Messages['errorBoundary'];
}

class ErrorBoundary extends React.Component<BoundaryProps, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  render(): React.ReactNode {
    if (!this.state.error) return this.props.children;
    return (
      <Box sx={{ alignItems: 'center', display: 'flex', justifyContent: 'center', minHeight: '100vh', p: 2 }}>
        <Paper variant="outlined" sx={{ maxWidth: 520, p: 4, width: '100%' }}>
          <AlertTriangle aria-hidden="true" size={30} />
          <Typography component="h1" fontSize={20} fontWeight={750} mt={2}>
            {this.props.messages.title}
          </Typography>
          <Typography color="text.secondary" mt={1}>
            {this.props.messages.description}
          </Typography>
          <Button onClick={() => window.location.reload()} startIcon={<RotateCcw size={17} />} sx={{ mt: 3 }} variant="contained">
            {this.props.messages.refresh}
          </Button>
        </Paper>
      </Box>
    );
  }
}

export const AppErrorBoundary: React.FC<React.PropsWithChildren> = ({ children }) => {
  const { messages } = useI18n();
  return <ErrorBoundary messages={messages.errorBoundary}>{children}</ErrorBoundary>;
};
