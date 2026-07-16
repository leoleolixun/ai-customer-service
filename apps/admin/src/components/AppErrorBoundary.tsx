import { AlertTriangle, RotateCcw } from 'lucide-react';
import { Box, Button, Paper, Typography } from '@mui/material';
import React from 'react';

interface State {
  error: Error | null;
}

export class AppErrorBoundary extends React.Component<React.PropsWithChildren, State> {
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
            The console could not be loaded
          </Typography>
          <Typography color="text.secondary" mt={1}>
            Refresh the page. If the problem continues, contact the platform administrator.
          </Typography>
          <Button onClick={() => window.location.reload()} startIcon={<RotateCcw size={17} />} sx={{ mt: 3 }} variant="contained">
            Refresh
          </Button>
        </Paper>
      </Box>
    );
  }
}
