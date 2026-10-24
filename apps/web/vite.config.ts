import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const target = process.env.API_PROXY_TARGET ?? 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/v1': { target, changeOrigin: true },
      '/health': { target, changeOrigin: true },
    },
  },
})
