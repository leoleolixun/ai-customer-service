import { fileURLToPath, URL } from 'node:url';
import { defineConfig } from 'vite';

export default defineConfig({
  resolve: {
    alias: {
      '@ai-support/sdk': fileURLToPath(new URL('../../packages/sdk/src/index.ts', import.meta.url)),
      '@ai-support/widget': fileURLToPath(
        new URL('../../packages/widget/src/index.tsx', import.meta.url),
      ),
    },
  },
  server: { port: 5174 },
  build: { sourcemap: true },
});
