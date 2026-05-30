import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// Test-only config, kept separate from vite.config.ts so the Tauri dev-server
// options there don't leak into the runner. Tailwind is omitted on purpose:
// these are behavioural tests against the DOM, not visual ones.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
    css: false,
    // Reset call history (not implementations) before each test, so module-level
    // vi.mock() stand-ins keep their behaviour while counts start clean.
    clearMocks: true,
  },
});
