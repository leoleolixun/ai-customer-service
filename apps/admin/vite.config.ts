import react from '@vitejs/plugin-react';
import { fileURLToPath, URL } from 'node:url';
import { defineConfig } from 'vite';

export default defineConfig(({ mode }) => ({
  base: mode === 'production' ? '/console/' : '/',
  plugins: [react()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    port: 5173,
    proxy: {
      '/v1': 'http://127.0.0.1:8000',
      '/health': 'http://127.0.0.1:8000',
    },
  },
  build: {
    sourcemap: false,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (
            id.includes('/react/') ||
            id.includes('/react-dom/') ||
            id.includes('/@mui/') ||
            id.includes('/@emotion/')
          ) return 'ui-vendor';
          if (id.includes('/@tanstack/')) return 'tanstack-vendor';
          if (id.includes('/lucide-react/')) return 'icons-vendor';
          return undefined;
        },
      },
    },
  },
}));
