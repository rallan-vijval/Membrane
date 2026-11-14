import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// The browser only ever talks to /api. Keys and the MongoDB URI stay in the backend.
export default defineConfig({
  plugins: [react()],
  build: { target: 'esnext' }, // pdf.js uses top-level await
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    proxy: { '/api': { target: 'http://127.0.0.1:8000', changeOrigin: false } },
  },
});
