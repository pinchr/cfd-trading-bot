import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  base: "./",
  server: {
    port: 5173,
    allowedHosts: [
      "unramped-melania-benzylidene.ngrok-free.dev",
      "localhost",
      "127.0.0.1",
    ],
    proxy: {
      "/cfd/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/cfd\/api/, "/api"),
      },
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
