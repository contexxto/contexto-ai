import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { readFileSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'

// ID único por build: en Vercel usa el SHA del commit; en local, la marca de tiempo.
// Se sella en sw.js para (1) versionar la caché del shell y (2) que el archivo cambie
// byte-a-byte en cada deploy → el navegador detecta un SW nuevo, que es el gatillo del
// auto-update. Sin esto, sw.js sería idéntico entre deploys y el navegador nunca lo
// actualizaría.
const BUILD_ID = (process.env.VERCEL_GIT_COMMIT_SHA || '').slice(0, 12) || String(Date.now())

// Sella el placeholder __BUILD_ID__ en el sw.js ya copiado a dist/ (public/ se copia tal cual,
// así que lo parcheamos post-build).
function stampServiceWorker() {
  return {
    name: 'stamp-sw-build-id',
    apply: 'build',
    writeBundle(options) {
      try {
        const swPath = resolve(options.dir || 'dist', 'sw.js')
        const src = readFileSync(swPath, 'utf8')
        writeFileSync(swPath, src.replace(/__BUILD_ID__/g, BUILD_ID))
      } catch (e) {
        console.warn('[stamp-sw] no se pudo sellar sw.js:', e.message)
      }
    },
  }
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), stampServiceWorker()],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
