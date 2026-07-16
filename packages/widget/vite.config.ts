import { defineConfig } from 'vite';
import dts from 'vite-plugin-dts';

export default defineConfig({
  plugins: [dts({ insertTypesEntry: true })],
  build: {
    lib: {
      entry: 'src/index.tsx',
      name: 'AISupportWidget',
      formats: ['es', 'iife'],
      fileName: (format) => format === 'iife' ? 'ai-support-widget.js' : 'index.js',
    },
    sourcemap: false,
    cssCodeSplit: false,
  },
});
