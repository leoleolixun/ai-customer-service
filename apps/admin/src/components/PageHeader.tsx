import { Box, Button, Typography } from '@mui/material';
import type { LucideIcon } from 'lucide-react';
import React, { useEffect } from 'react';

import { useI18n } from '@/i18n/I18nProvider';

interface PageHeaderProps {
  title: string;
  description?: string;
  action?: { label: string; icon: LucideIcon; onClick: () => void };
}

const PageHeader: React.FC<PageHeaderProps> = ({ title, description, action }) => {
  const { messages } = useI18n();

  useEffect(() => {
    document.title = `${title} · ${messages.app.name}`;
  }, [messages.app.name, title]);

  return (
    <Box
      sx={{
        alignItems: { sm: 'center' },
        display: 'flex',
        flexDirection: { xs: 'column', sm: 'row' },
        gap: 2,
        justifyContent: 'space-between',
        mb: 3,
      }}
    >
      <Box>
        <Typography component="h1" variant="h1">{title}</Typography>
        {description && <Typography color="text.secondary" sx={{ mt: 0.5 }}>{description}</Typography>}
      </Box>
      {action && (
        <Button variant="contained" startIcon={<action.icon size={17} />} onClick={action.onClick}>
          {action.label}
        </Button>
      )}
    </Box>
  );
};

export default PageHeader;
