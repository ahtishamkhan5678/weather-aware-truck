/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // In dev the Django API runs on :8000; in production Django serves this build.
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    chunkSizeWarningLimit: 1100, // maplibre-gl is ~1 MB and only loaded on /planner
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('maplibre-gl')) return 'maplibre'
          if (id.includes('node_modules')) return 'vendor'
        },
      },
    },
  },
  test: { environment: 'node', include: ['src/**/*.test.ts'], exclude: ['e2e/**'] },
})
