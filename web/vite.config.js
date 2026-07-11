import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/camera': 'http://127.0.0.1:8000',
      '/ask': 'http://127.0.0.1:8000',
      '/reveal': 'http://127.0.0.1:8000',
      '/gesture': 'http://127.0.0.1:8000',
      '/context': 'http://127.0.0.1:8000',
      '/status': 'http://127.0.0.1:8000',
      '/ws': { target: 'ws://127.0.0.1:8000', ws: true },
    }
  }
})
