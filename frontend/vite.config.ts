import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5642,
    strictPort: true,
    proxy: {
      '/api': {
        // literal IPv4: `localhost` can resolve to an unrelated IPv6 service on this machine
        target: 'http://127.0.0.1:8642',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
