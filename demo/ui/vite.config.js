import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
// Proxies /api/* to the Flask demo server so the React app and the Flask app
// can run on different ports without CORS noise in dev. The browser only ever
// calls same-origin /api/* and never sees the LiteLLM key.
export default defineConfig({
    plugins: [react()],
    server: {
        port: Number(process.env.PORT) || 3000,
        proxy: {
            "/api": {
                target: "http://127.0.0.1:5001",
                changeOrigin: true,
            },
        },
    },
});
