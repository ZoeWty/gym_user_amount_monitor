import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  // GitHub Pages serves this repo under /<repo-name>/, not at the domain root,
  // so every asset URL needs that prefix. Empty for the Docker build, which is
  // served at /.
  base: process.env.VITE_BASE || '/',
  // Dev only. In production the SPA is served by FastAPI from the same
  // origin, so there is no CORS configuration anywhere in this project.
  server: { proxy: { '/api': 'http://localhost:8000' } },
})
