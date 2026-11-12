import { describe, expect, it } from "vitest";
import { z } from "zod";
import { defineQueue, emailMessage, jobIdFor } from "../src/index.ts";

describe("queue definitions", () => {
  it("rejects names that do not follow area.action", () => {
    expect(() =>
      defineQueue({
        name: "Email",
        schema: z.object({}),
        retryLimit: 1,
        retryDelaySeconds: 1,
        retryBackoff: false,
        expireInSeconds: 1,
        idempotencyKey: () => undefined,
      }),
    ).toThrow(/area\.action/);
  });

  it("validates email messages by template", () => {
    expect(
      emailMessage.safeParse({ template: "verify-email", to: "a@b.test", name: "A", url: "x" })
        .success,
    ).toBe(false);
    expect(
      emailMessage.safeParse({
        template: "verify-email",
        to: "a@b.test",
        name: "A",
        url: "https://orrery.test/v",
      }).success,
    ).toBe(true);
    expect(emailMessage.safeParse({ template: "unknown", to: "a@b.test", name: "A" }).success).toBe(
      false,
    );
  });
});

describe("job ids", () => {
  it("are stable per queue and key, and differ across queues and keys", () => {
    expect(jobIdFor("email.send", "a")).toBe(jobIdFor("email.send", "a"));
    expect(jobIdFor("email.send", "a")).not.toBe(jobIdFor("email.send", "b"));
    expect(jobIdFor("email.send", "a")).not.toBe(jobIdFor("objects.delete", "a"));
    expect(jobIdFor("email.send", "a")).toMatch(/^[0-9a-f-]{8}-[0-9a-f]{4}-5/);
  });
});
