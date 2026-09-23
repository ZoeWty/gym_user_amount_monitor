import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  // Dev only. In production the SPA is served by FastAPI from the same
  // origin, so there is no CORS configuration anywhere in this project.
  server: { proxy: { '/api': 'http://localhost:8000' } },
})
