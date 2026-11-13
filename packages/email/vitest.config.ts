import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: ["test/**/*.test.{ts,tsx}"],
    testTimeout: 30_000,
    // Containers start slowly while every package's suite starts its own at once.
    hookTimeout: 180_000,
  },
});
