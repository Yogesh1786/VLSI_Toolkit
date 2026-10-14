import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

declare const process: { env: Record<string, string | undefined> };

// During development the React app runs on :5173 and forwards /api calls to
// the Python API server on :8000 (python -m uvicorn api.main:app --port 8000).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    // API_TARGET lets you point the dev server at another API, e.g. API_TARGET=http://localhost:8001
    proxy: { "/api": process.env.API_TARGET ?? "http://localhost:8000" },
  },
  build: { outDir: "dist", chunkSizeWarningLimit: 1500 },
});
