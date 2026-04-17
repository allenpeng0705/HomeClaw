import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

/**
 * Dev server proxies /api → Portal so browser calls stay same-origin (no CORS).
 * Set portal port via env PORTAL_TARGET (default HomeClaw Portal 18472).
 */
const portalTarget = process.env.PORTAL_TARGET || "http://127.0.0.1:18472";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5175,
    proxy: {
      "/api": {
        target: portalTarget,
        changeOrigin: true,
      },
    },
  },
});
