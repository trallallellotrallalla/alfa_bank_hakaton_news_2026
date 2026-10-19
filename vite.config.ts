import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Прокси на реальный бэкенд в dev-режиме: VITE_API_MODE=http, VITE_API_PROXY=http://localhost:8000
const proxyTarget = process.env.VITE_API_PROXY;

export default defineConfig({
    plugins: [react()],
    server: {
        port: 5173,
        host: true,
        proxy: proxyTarget
            ? { '/api': { target: proxyTarget, changeOrigin: true, rewrite: (p) => p.replace(/^\/api/, '') } }
            : undefined,
    },
});
