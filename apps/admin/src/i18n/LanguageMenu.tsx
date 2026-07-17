import { Languages } from 'lucide-react';
import { Button, Menu, MenuItem } from '@mui/material';
import React, { useState } from 'react';

import { type Language, useI18n } from '@/i18n/I18nProvider';

interface LanguageMenuProps {
  color?: 'inherit' | 'primary';
  compact?: boolean;
}

const LanguageMenu: React.FC<LanguageMenuProps> = ({ color = 'primary', compact = false }) => {
  const { language, messages, setLanguage } = useI18n();
  const [anchorElement, setAnchorElement] = useState<HTMLElement | null>(null);
  const label = language === 'en' ? messages.language.english : messages.language.simplifiedChinese;

  const selectLanguage = (nextLanguage: Language): void => {
    setLanguage(nextLanguage);
    setAnchorElement(null);
  };

  return (
    <>
      <Button
        aria-label={messages.language.change}
        aria-controls={anchorElement ? 'language-menu' : undefined}
        aria-expanded={anchorElement ? 'true' : undefined}
        aria-haspopup="menu"
        color={color}
        onClick={(event) => setAnchorElement(event.currentTarget)}
        size="small"
        startIcon={<Languages aria-hidden="true" size={17} />}
        sx={compact ? { minWidth: 0, px: 1 } : undefined}
      >
        {label}
      </Button>
      <Menu
        id="language-menu"
        anchorEl={anchorElement}
        open={Boolean(anchorElement)}
        onClose={() => setAnchorElement(null)}
        MenuListProps={{ 'aria-label': messages.language.change }}
      >
        <MenuItem selected={language === 'en'} onClick={() => selectLanguage('en')}>
          {messages.language.english}
        </MenuItem>
        <MenuItem selected={language === 'zh-CN'} onClick={() => selectLanguage('zh-CN')}>
          {messages.language.simplifiedChinese}
        </MenuItem>
      </Menu>
    </>
  );
};

export default LanguageMenu;
