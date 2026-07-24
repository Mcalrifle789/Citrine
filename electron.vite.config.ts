import { defineConfig } from 'electron-vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'node:path'

export default defineConfig({
  main: {
    build: { lib: { entry: resolve(__dirname, 'electron/main.ts') } },
  },
  preload: {
    // A sandboxed preload must be CommonJS, and package.json sets
    // "type": "module" — which makes the default output preload.mjs, an ESM
    // file Electron will not load as a preload. Pin the format and the
    // extension so the emitted name matches what main.ts references.
    build: {
      lib: {
        entry: resolve(__dirname, 'electron/preload.ts'),
        formats: ['cjs'],
        fileName: () => 'preload.cjs',
      },
    },
  },
  renderer: {
    root: '.',
    build: { rollupOptions: { input: resolve(__dirname, 'index.html') } },
    plugins: [react()],
    resolve: { alias: { '@': resolve(__dirname, 'src') } },
  },
})
