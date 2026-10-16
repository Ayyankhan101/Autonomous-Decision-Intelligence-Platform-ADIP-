import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
  ],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8200',
        changeOrigin: true,
      },
    },
  },
  build: {
    rolldownOptions: {
      output: {
        codeSplitting: {
          groups: [
            {
              name: 'vendor-react',
              test: /node_modules[\\/](react|react-dom|scheduler)[\\/]/,
            },
            {
              name: 'vendor-three',
              test: /node_modules[\\/](three|@react-three|three-stdlib|maath|camera-controls|suspend-react|its-fine|zustand)[\\/]/,
            },
            {
              name: 'vendor-leaflet',
              test: /node_modules[\\/](leaflet|react-leaflet)[\\/]/,
            },
          ],
        },
      },
    },
  },
})
