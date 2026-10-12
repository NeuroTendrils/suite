import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// UI interaction tests (jsdom). Pure helpers keep using `node --test` (tests/*.test.ts).
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    include: ["tests/ui/**/*.test.tsx"],
    setupFiles: ["tests/ui/setup.ts"],
  },
});
