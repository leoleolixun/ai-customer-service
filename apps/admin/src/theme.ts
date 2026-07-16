import { createTheme } from '@mui/material/styles';

export const theme = createTheme({
  palette: {
    mode: 'light',
    primary: { main: '#147a5b', dark: '#0d6047', light: '#d8eee6' },
    secondary: { main: '#ba6a12' },
    background: { default: '#f4f6f5', paper: '#ffffff' },
    text: { primary: '#17211d', secondary: '#63706a' },
    divider: '#dce3df',
  },
  shape: { borderRadius: 6 },
  typography: {
    fontFamily: 'Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
    h1: { fontSize: '1.5rem', fontWeight: 700 },
    h2: { fontSize: '1.1rem', fontWeight: 700 },
    button: { textTransform: 'none', fontWeight: 650 },
  },
  components: {
    MuiButton: { defaultProps: { disableElevation: true } },
    MuiPaper: { styleOverrides: { root: { backgroundImage: 'none' } } },
    MuiCard: { styleOverrides: { root: { borderRadius: 6 } } },
  },
});
