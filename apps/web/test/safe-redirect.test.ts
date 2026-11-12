import fc from "fast-check";
import { describe, expect, it } from "vitest";
import { safeRedirect } from "../src/lib/safe-redirect.ts";

const BASE = "https://orrery.test";

describe("safeRedirect", () => {
  it("keeps same-origin paths with their query and hash", () => {
    expect(safeRedirect("/account?tab=sessions#passkeys")).toBe("/account?tab=sessions#passkeys");
  });

  it.each([
    "//evil.example/path",
    "/\\evil.example",
    "https://evil.example",
    "javascript:alert(1)",
    "account",
    "/\t/evil.example",
    "",
  ])("rejects %j", (target) => {
    expect(safeRedirect(target, "/fallback")).toBe("/fallback");
  });

  it("never yields a destination that resolves to another origin", () => {
    fc.assert(
      fc.property(fc.string({ maxLength: 60 }), (target) => {
        const result = safeRedirect(target, "/fallback");
        expect(new URL(result, BASE).origin).toBe(BASE);
      }),
      { numRuns: 2000 },
    );
  });
});
