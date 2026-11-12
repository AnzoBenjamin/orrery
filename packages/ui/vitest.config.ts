import { defineConfig } from "vitest/config";

// Node by default. Component tests opt into the DOM with a `// @vitest-environment jsdom` header.
export default defineConfig({
  test: { include: ["test/**/*.test.{ts,tsx}"], environment: "node" },
});
