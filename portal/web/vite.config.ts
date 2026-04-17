import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

/** Built assets are served under Portal's /static mount. */
export default defineConfig({
  plugins: [react()],
  base: "/static/app/",
  build: {
    outDir: "../static/app",
    emptyOutDir: true,
  },
});
