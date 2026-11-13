import { schema } from "@orrery/db";
import { describe, expect, it } from "vitest";
import { accountLimitFor, checkAccountLimit } from "../../src/server/account-limits.ts";
import { createLimits, limitPolicies, waitText } from "../../src/server/rate-limits.ts";
import { withTestDatabase } from "./support.ts";

const database = withTestDatabase();

async function attempts(path: string, email: string, count: number) {
  const limit = createLimits(database().pool);
  const results: (string | null)[] = [];
  for (let i = 0; i < count; i++) results.push(await checkAccountLimit(limit, path, { email }));
  return results;
}

describe("per-account auth limits", () => {
  it("refuses sign-in for one account past its limit, whatever the address's case", async () => {
    const allowed = limitPolicies["sign-in-account"].points;
    const results = [
      ...(await attempts("/sign-in/email", "Restorer@Example.com", allowed - 1)),
      ...(await attempts("/sign-in/email", "  restorer@example.com ", 2)),
    ];
    expect(results.slice(0, allowed).every((r) => r === null)).toBe(true);
    expect(results[allowed]).toMatch(
      "Too many attempts for this account. Wait 15 minutes, then try again.",
    );
    // Another account is unaffected.
    expect(await attempts("/sign-in/email", "conservator@example.com", 1)).toEqual([null]);
  });

  it("limits password reset requests per address, existing or not", async () => {
    const allowed = limitPolicies["password-reset-account"].points;
    const results = await attempts("/request-password-reset", "nobody@example.com", allowed + 1);
    expect(results.slice(0, allowed)).toEqual(Array(allowed).fill(null));
    expect(results[allowed]).toMatch(/^Too many attempts for this account\./);
  });

  it("counts each endpoint separately and ignores requests without an address", async () => {
    const resets = limitPolicies["password-reset-account"].points;
    await attempts("/request-password-reset", "maker@example.com", resets + 1);
    expect(await attempts("/sign-in/email", "maker@example.com", 1)).toEqual([null]);
    expect(accountLimitFor("/sign-in/email", {})).toBeNull();
    expect(accountLimitFor("/sign-in/email", { email: "  " })).toBeNull();
    expect(accountLimitFor("/get-session", { email: "maker@example.com" })).toBeNull();
  });

  it("states short waits in seconds and long ones in whole minutes", () => {
    expect(waitText(1)).toBe("1 second");
    expect(waitText(45_200)).toBe("46 seconds");
    expect(waitText(119_000)).toBe("119 seconds");
    expect(waitText(120_000)).toBe("2 minutes");
    expect(waitText(899_400)).toBe("15 minutes");
  });

  it("stores a digest, never the address", async () => {
    const applies = accountLimitFor("/sign-up/email", { email: "Maker@Example.com" });
    expect(applies?.name).toBe("sign-up-account");
    expect(applies?.key).toMatch(/^[0-9a-f]{64}$/);
    await attempts("/sign-up/email", "maker@example.com", 1);
    const rows = await database()
      .db.select({ key: schema.requestLimit.key })
      .from(schema.requestLimit);
    expect(rows.length).toBeGreaterThan(0);
    expect(rows.some((r) => r.key.includes("example.com"))).toBe(false);
  });
});
