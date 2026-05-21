import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      // Source-tree aliases (Phase 2 refactor)
      '@':           path.resolve(__dirname, 'src'),
      '@components': path.resolve(__dirname, 'src/components'),
      '@pages':      path.resolve(__dirname, 'src/pages'),
      '@hooks':      path.resolve(__dirname, 'src/hooks'),
      '@lib':        path.resolve(__dirname, 'src/lib'),
      '@types':      path.resolve(__dirname, 'src/types'),
      '@contexts':   path.resolve(__dirname, 'src/contexts'),
      // External: theory docs (markdown)
      '@docs':       path.resolve(__dirname, '../docs/stock_theory'),
    }
  }
})
