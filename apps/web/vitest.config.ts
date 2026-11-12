import { defineConfig } from "vitest/config";

export default defineConfig({
  test: { include: ["test/**/*.test.{ts,tsx}"], hookTimeout: 180_000, testTimeout: 60_000 },
});
