import react from '@vitejs/plugin-react';
import { fileURLToPath, URL } from 'node:url';
import { defineConfig } from 'vitest/config';

const pathFromRoot = (path: string) => fileURLToPath(new URL(path, import.meta.url));

export default defineConfig({
  test: {
    projects: [
      {
        root: pathFromRoot('./packages/sdk'),
        test: {
          environment: 'node',
          include: ['src/**/*.test.ts'],
          name: 'sdk',
        },
      },
      {
        plugins: [react()],
        root: pathFromRoot('./packages/widget'),
        resolve: {
          alias: {
            '@ai-support/sdk': pathFromRoot('./packages/sdk/src/index.ts'),
          },
        },
        test: {
          environment: 'jsdom',
          include: ['src/**/*.test.tsx'],
          name: 'widget',
          restoreMocks: true,
        },
      },
      {
        plugins: [react()],
        root: pathFromRoot('./apps/admin'),
        resolve: {
          alias: {
            '@': pathFromRoot('./apps/admin/src'),
          },
        },
        test: {
          environment: 'jsdom',
          include: ['src/**/*.test.{ts,tsx}'],
          name: 'admin',
          restoreMocks: true,
        },
      },
      {
        root: pathFromRoot('./apps/demo'),
        test: {
          environment: 'node',
          include: ['src/**/*.test.ts'],
          name: 'demo',
        },
      },
    ],
  },
});
