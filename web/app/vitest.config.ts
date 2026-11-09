import path from "node:path";

import { defineConfig } from "vitest/config";

// Unit tests for pure functions only (the agent stream parser and turn
// reducer). No DOM: components are checked in the browser.
export default defineConfig({
  resolve: { alias: { "@": path.resolve(__dirname, "src") } },
  test: {
    include: ["src/**/*.test.ts"],
    environment: "node",
  },
});
