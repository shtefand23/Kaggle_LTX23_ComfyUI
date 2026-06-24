/// <reference types="vite/client" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// GitHub Pages constants for THIS repo
const GH_PAGES_BASE = '/Kaggle_Workspace_FreeGPU/';

export default defineConfig(({ mode }) => {
  return {
    // base MUST match the GitHub Pages subpath, otherwise assets 404.
    base: GH_PAGES_BASE,
    plugins: [react()],
    server: {
      port: 5173,
      strictPort: false,
      open: false,
    },
    build: {
      // Output to docs-site/dist so the existing user never breaks
      // anything else, and upload-pages-artifact@v3 picks up exactly.
      outDir: 'docs-site/dist',
      emptyOutDir: true,
      sourcemap: mode !== 'production',
      target: 'es2020',
      cssCodeSplit: true,
      terserOptions: {
        compress: { drop_console: false }, // keep console for dev/debug paranoia
      },
      rollupOptions: {
        output: {
          manualChunks: {
            'react-vendor': ['react', 'react-dom', 'react-router-dom'],
            'motion-vendor': ['framer-motion'],
          },
        },
      },
    },
    optimizeDeps: {
      include: ['react', 'react-dom', 'react-router-dom', 'framer-motion'],
    },
  };
});
