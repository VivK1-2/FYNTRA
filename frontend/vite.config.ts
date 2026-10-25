import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// The backend API key lives ONLY here (read from .env, no VITE_ prefix), so it is
// attached by the local server and never shipped to the browser bundle.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "");
  const target = env.BACKEND_URL || "http://127.0.0.1:8000";
  const key = env.FYNTRA_API_KEY || "";

  const proxy = {
    "/api": {
      target,
      changeOrigin: true,
      headers: (key ? { "X-API-Key": key } : {}) as Record<string, string>,
    },
    "/health": { target, changeOrigin: true },
  };

  return {
    plugins: [react()],
    server: { host: "127.0.0.1", port: 5173, proxy },
    preview: { host: "127.0.0.1", port: 5173, proxy },
  };
});
