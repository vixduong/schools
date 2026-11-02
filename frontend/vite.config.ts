import path from "node:path";
import tailwindcss from "@tailwindcss/vite";
import { tanstackRouter } from "@tanstack/router-plugin/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [tanstackRouter({ target: "react", autoCodeSplitting: true }), react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(import.meta.dirname, "src") } },
  server: {
    // Same origin as the API in dev (ADR 0003): Django answers /api on :8000. Django picks the
    // School from the host (a.localhost), so the proxy keeps the browser's Host header.
    // API_PORT: another Django port (make smoke runs its own on a free one).
    proxy: {
      "/api": { target: `http://localhost:${process.env.API_PORT ?? 8000}`, changeOrigin: false },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
  },
});
