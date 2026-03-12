import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": "/src",
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8020",
      "/auth": "http://localhost:8020",
      "/health": "http://localhost:8020",
    },
  },
});
