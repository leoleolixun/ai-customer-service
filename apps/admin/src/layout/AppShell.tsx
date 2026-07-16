import {
  Activity,
  AppWindow,
  Bot,
  Headphones,
  KeyRound,
  LayoutDashboard,
  Library,
  LogOut,
  Menu,
  Users,
} from 'lucide-react';
import {
  AppBar,
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  Drawer,
  IconButton,
  LinearProgress,
  List,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Toolbar,
  TextField,
  Tooltip,
  Typography,
  useMediaQuery,
} from '@mui/material';
import { Outlet, useLocation, useNavigate } from '@tanstack/react-router';
import React, { Suspense, useEffect, useRef, useState } from 'react';

import { api, errorMessage } from '@/api/client';
import { useAuth } from '@/auth/AuthProvider';

const drawerWidth = 232;

const AppShell: React.FC = () => {
  const { user, checking, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const compact = useMediaQuery('(max-width:900px)');
  const [mobileOpen, setMobileOpen] = useState(false);
  const [passwordOpen, setPasswordOpen] = useState(false);
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [passwordBusy, setPasswordBusy] = useState(false);
  const redirecting = useRef(false);

  useEffect(() => {
    if (!checking && !user && !redirecting.current) {
      redirecting.current = true;
      void navigate({ to: '/login', replace: true });
    }
  }, [checking, navigate, user]);

  if (checking) return <LinearProgress aria-label="Checking session" />;
  if (!user) return <LinearProgress aria-label="Redirecting to sign in" />;

  const closePasswordDialog = (): void => {
    if (passwordBusy) return;
    setPasswordOpen(false);
    setCurrentPassword('');
    setNewPassword('');
    setConfirmPassword('');
    setPasswordError(null);
  };

  const changePassword = async (): Promise<void> => {
    if (newPassword !== confirmPassword) {
      setPasswordError('The new passwords do not match.');
      return;
    }
    setPasswordBusy(true);
    setPasswordError(null);
    try {
      await api('/v1/admin/auth/change-password', {
        method: 'POST',
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: newPassword,
        }),
      });
      logout();
      await navigate({ to: '/login' });
    } catch (cause) {
      setPasswordError(errorMessage(cause));
    } finally {
      setPasswordBusy(false);
    }
  };

  const adminItems = [
    { label: 'Overview', path: '/', icon: LayoutDashboard },
    { label: 'Applications', path: '/applications', icon: AppWindow },
    { label: 'AI models', path: '/ai', icon: Bot },
    { label: 'Knowledge', path: '/knowledge', icon: Library },
    { label: 'Team', path: '/team', icon: Users },
    { label: 'Operations', path: '/operations', icon: Activity },
  ];
  const agentItems = [
    { label: 'Agent workspace', path: '/handoffs', icon: Headphones },
  ];
  const platformItems = [
    { label: 'Platform overview', path: '/', icon: LayoutDashboard },
    { label: 'Tenants', path: '/platform', icon: Users },
  ];
  const items = user.is_platform_admin && !user.tenant_id
    ? platformItems
    : user.role === 'agent'
      ? agentItems
      : [...adminItems, ...agentItems];

  const drawer = (
    <Box sx={{ bgcolor: '#17211d', color: '#fff', display: 'flex', flexDirection: 'column', height: '100%' }}>
      <Toolbar sx={{ gap: 1.25, minHeight: '64px !important', px: 2 }}>
        <Box sx={{ alignItems: 'center', bgcolor: '#d8eee6', borderRadius: 1, color: '#0d6047', display: 'flex', height: 34, justifyContent: 'center', width: 34 }}>
          <Headphones size={19} aria-hidden="true" />
        </Box>
        <Typography fontWeight={750}>Support Console</Typography>
      </Toolbar>
      <Divider sx={{ borderColor: 'rgba(255,255,255,.1)' }} />
      <List sx={{ flex: 1, px: 1, py: 1.5 }}>
        {items.map((item) => {
          const selected = item.path === '/' ? location.pathname === '/' : location.pathname.startsWith(item.path);
          return (
            <ListItemButton
              key={item.path}
              selected={selected}
              onClick={() => {
                void navigate({ to: item.path });
                setMobileOpen(false);
              }}
              sx={{
                borderRadius: 1,
                color: '#c7d1cc',
                mb: 0.5,
                '&.Mui-selected': { bgcolor: 'rgba(80,186,147,.18)', color: '#fff' },
                '&.Mui-selected:hover': { bgcolor: 'rgba(80,186,147,.24)' },
                '&:hover': { bgcolor: 'rgba(255,255,255,.07)' },
              }}
            >
              <ListItemIcon sx={{ color: 'inherit', minWidth: 36 }}><item.icon size={18} /></ListItemIcon>
              <ListItemText primary={item.label} primaryTypographyProps={{ fontSize: 14, fontWeight: 600 }} />
            </ListItemButton>
          );
        })}
      </List>
      <Divider sx={{ borderColor: 'rgba(255,255,255,.1)' }} />
      <Box sx={{ alignItems: 'center', display: 'flex', gap: 1, minWidth: 0, p: 1.5 }}>
        <Box sx={{ minWidth: 0, flex: 1 }}>
          <Typography fontSize={12} noWrap>{user.email}</Typography>
          <Typography color="#9caaa3" fontSize={11}>{user.role?.replace('_', ' ')}</Typography>
        </Box>
        <Tooltip title="Change password">
          <IconButton
            aria-label="Change password"
            color="inherit"
            size="small"
            onClick={() => {
              setPasswordOpen(true);
              setMobileOpen(false);
            }}
          >
            <KeyRound size={17} />
          </IconButton>
        </Tooltip>
        <Tooltip title="Sign out">
          <IconButton
            color="inherit"
            size="small"
            onClick={() => {
              logout();
              void navigate({ to: '/login' });
            }}
          >
            <LogOut size={17} />
          </IconButton>
        </Tooltip>
      </Box>
    </Box>
  );

  return (
    <>
      <Box sx={{ display: 'flex', minHeight: '100vh' }}>
      {compact ? (
        <Drawer open={mobileOpen} onClose={() => setMobileOpen(false)} sx={{ '& .MuiDrawer-paper': { width: drawerWidth } }}>
          {drawer}
        </Drawer>
      ) : (
        <Drawer variant="permanent" sx={{ width: drawerWidth, '& .MuiDrawer-paper': { width: drawerWidth } }}>
          {drawer}
        </Drawer>
      )}
      <Box component="main" sx={{ flex: 1, minWidth: 0 }}>
        {compact && (
          <AppBar color="inherit" elevation={0} position="sticky" sx={{ borderBottom: 1, borderColor: 'divider' }}>
            <Toolbar>
              <IconButton edge="start" onClick={() => setMobileOpen(true)} aria-label="Open navigation">
                <Menu size={21} />
              </IconButton>
              <Typography fontWeight={700} sx={{ ml: 1 }}>Support Console</Typography>
            </Toolbar>
          </AppBar>
        )}
        <Box sx={{ mx: 'auto', maxWidth: 1440, px: { xs: 2, md: 4 }, py: { xs: 2.5, md: 4 } }}>
          <Suspense fallback={<LinearProgress aria-label="Loading page" />}>
            <Outlet />
          </Suspense>
        </Box>
      </Box>
      </Box>
      <Dialog open={passwordOpen} onClose={closePasswordDialog} fullWidth maxWidth="xs">
        <DialogTitle>Change password</DialogTitle>
        <DialogContent sx={{ display: 'grid', gap: 2, pt: '8px !important' }}>
          {passwordError && <Alert severity="error">{passwordError}</Alert>}
          <TextField
            autoComplete="current-password"
            label="Current password"
            type="password"
            value={currentPassword}
            onChange={(event) => setCurrentPassword(event.target.value)}
          />
          <TextField
            autoComplete="new-password"
            helperText="At least 12 characters"
            label="New password"
            type="password"
            value={newPassword}
            onChange={(event) => setNewPassword(event.target.value)}
          />
          <TextField
            autoComplete="new-password"
            label="Confirm new password"
            type="password"
            value={confirmPassword}
            onChange={(event) => setConfirmPassword(event.target.value)}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={closePasswordDialog} disabled={passwordBusy}>Cancel</Button>
          <Button
            variant="contained"
            disabled={
              currentPassword.length < 8 ||
              newPassword.length < 12 ||
              confirmPassword.length < 12 ||
              passwordBusy
            }
            onClick={() => void changePassword()}
          >
            Change password
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
};

export default AppShell;
