import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"

const apiProxyTarget = process.env.VITE_API_PROXY_TARGET

export default defineConfig({
    plugins: [react()],
    server: {
        proxy: apiProxyTarget ? {
            "/api": {
                target: apiProxyTarget,
                changeOrigin: true,
            },
        } : undefined,
    },
})
