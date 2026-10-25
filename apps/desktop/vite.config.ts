import { defineConfig } from "vite";
import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  clearScreen: false,
  server: {
    port: 5173,
    strictPort: true,
    fs: {
      allow: [
        fileURLToPath(new URL(".", import.meta.url)),
        fileURLToPath(new URL("../../packages/theme", import.meta.url)),
        fileURLToPath(new URL("../neurolearn/app/assets/fonts", import.meta.url)),
      ],
    },
  },
  envPrefix: ["VITE_", "TAURI_"],
});
