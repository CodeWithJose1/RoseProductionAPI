import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// The GUI is served by Flask at /app/ in production. During development the
// Vite dev server proxies API calls to Flask so the browser stays same-origin
// (the HttpOnly session cookie then works without CORS).
const API_TARGET = process.env.ROSE_API_URL || 'http://127.0.0.1:7003';
const API_PREFIXES = [
  '/auth', '/farms', '/lots', '/varieties', '/crops', '/seasons',
  '/harvests', '/forecasts', '/stats',
];

export default defineConfig({
  base: '/app/',
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: Object.fromEntries(
      API_PREFIXES.map((prefix) => [prefix, { target: API_TARGET, changeOrigin: false }]),
    ),
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    sourcemap: false,
    chunkSizeWarningLimit: 900,
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.js'],
    include: ['src/**/*.test.{js,jsx}'],
    css: false,
  },
});
