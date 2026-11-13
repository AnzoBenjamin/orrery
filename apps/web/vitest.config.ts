import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: ["test/**/*.test.{ts,tsx}"],
    globalSetup: ["test/global-setup.ts"],
    hookTimeout: 180_000,
    testTimeout: 60_000,
  },
});
