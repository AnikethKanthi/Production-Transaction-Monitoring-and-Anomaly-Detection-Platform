import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: { manualChunks: {
        framework: ['react', 'react-dom', 'react-router-dom', '@tanstack/react-query'],
        charts: ['recharts'],
      } },
    },
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/openapi.json': process.env.API_PROXY_TARGET ?? 'http://127.0.0.1:8000',
      '/api': {
        target: process.env.API_PROXY_TARGET ?? 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
});
