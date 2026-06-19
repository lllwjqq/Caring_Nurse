import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Docker: API_PROXY_TARGET=http://backend:8000  |  Local: defaults to localhost:8000
const apiProxyTarget = process.env.API_PROXY_TARGET || 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: apiProxyTarget,
        changeOrigin: true,
      },
    },
  },
})
