import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { handleMultiplayerRequest } from './api/multiplayer-core.js'

export default defineConfig({
  plugins: [
    react(),
    {
      name: 'realcity-multiplayer-api',
      configureServer(server) {
        server.middlewares.use('/api/multiplayer', (req, res) => {
          handleMultiplayerRequest(req, res)
        })
      },
    },
  ],
  optimizeDeps: {
    exclude: ['@react-three/rapier'],
  },
  server: {
    proxy: {
      '/ollama': {
        target: 'http://localhost:11434',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/ollama/, ''),
      },
    },
  },
  build: {
    target: 'esnext',
    chunkSizeWarningLimit: 3000,
    rollupOptions: {
      output: {
        manualChunks: {
          three: ['three'],
          fx: ['postprocessing'],
        },
      },
    },
  },
})
