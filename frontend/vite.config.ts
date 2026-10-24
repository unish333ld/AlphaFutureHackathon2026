import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const target =
    process.env.BACKEND_URL ?? env.BACKEND_URL ?? "http://127.0.0.1:8000";
  return {
    plugins: [react()],
    server: {
      port: 5173,
      strictPort: true,
      proxy: Object.fromEntries(
        ["/api/", "/admin/", "/static/"].map((path) => [
          path,
          { target, changeOrigin: false },
        ]),
      ),
    },
    build: { sourcemap: false },
  };
});
