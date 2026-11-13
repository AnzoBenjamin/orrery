import { describe, expect, it } from "vitest";
import { createNonce, securityHeaders } from "../src/server/security-headers.ts";

const directives = (csp: string) =>
  Object.fromEntries(csp.split("; ").map((d) => [d.split(" ")[0], d.split(" ").slice(1)]));

describe("security headers", () => {
  it("allow scripts only with the request nonce, and only the object store besides this origin", () => {
    const headers = securityHeaders({
      nonce: "abc123==",
      objectStoreOrigin: "https://storage.orrery.example",
      production: true,
    });
    const csp = directives(headers["content-security-policy"] ?? "");
    expect(csp["script-src"]).toEqual(["'nonce-abc123=='", "'strict-dynamic'"]);
    expect(csp["style-src"]).toEqual(["'self'", "'nonce-abc123=='"]);
    expect(csp["connect-src"]).toEqual(["'self'", "https://storage.orrery.example"]);
    expect(csp["frame-ancestors"]).toEqual(["'none'"]);
    expect(csp["object-src"]).toEqual(["'none'"]);
    expect(csp["upgrade-insecure-requests"]).toEqual([]);
    expect(headers["strict-transport-security"]).toMatch(/max-age=\d+/);
    expect(headers["x-content-type-options"]).toBe("nosniff");
    expect(headers["permissions-policy"]).toContain("microphone=()");
  });

  it("relax only what the development server needs", () => {
    const headers = securityHeaders({
      nonce: "n",
      objectStoreOrigin: "http://localhost:53900",
      production: false,
    });
    const csp = directives(headers["content-security-policy"] ?? "");
    expect(csp["script-src"]).toEqual(["'nonce-n'", "'strict-dynamic'"]);
    expect(csp["connect-src"]).toContain("ws:");
    expect(headers["strict-transport-security"]).toBeUndefined();
  });

  it("makes a fresh 128-bit nonce each time", () => {
    const a = createNonce();
    expect(atob(a)).toHaveLength(16);
    expect(createNonce()).not.toBe(a);
  });
});
