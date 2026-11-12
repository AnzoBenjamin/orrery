import type { EmailMessage } from "@orrery/jobs";
import { describe, expect, it } from "vitest";
import { renderEmail } from "../src/index.ts";

const base = { to: "ada@orrery.test", name: "Ada" };
const messages: EmailMessage[] = [
  { ...base, template: "verify-email", url: "https://orrery.test/verify?token=v1" },
  { ...base, template: "reset-password", url: "https://orrery.test/reset?token=r1" },
  {
    ...base,
    template: "sign-in-alert",
    at: "2026-11-13T09:30:00.000Z",
    device: "Firefox on Linux",
    ipPrefix: "203.0.x.x",
    sessionsUrl: "https://orrery.test/account/sessions",
  },
  {
    ...base,
    template: "analysis-complete",
    specimenTitle: "Singer 66 treadle",
    url: "https://orrery.test/specimens/1",
    preferencesUrl: "https://orrery.test/account/email",
  },
];

describe.each(messages)("$template email", (message) => {
  it("renders a subject, HTML, and a plain-text part that carry the message", async () => {
    const rendered = await renderEmail(message);
    expect(rendered.subject.length).toBeGreaterThan(5);
    expect(rendered.html).toContain("<html");
    expect(rendered.html).toContain("Ada");
    expect(rendered.text).toContain("Ada");
    for (const value of Object.values(message)) {
      if (typeof value === "string" && value.startsWith("https://")) {
        expect(rendered.html).toContain(value);
        expect(rendered.text).toContain(value);
      }
    }
    expect(rendered.html).not.toMatch(/undefined|NaN|\[object Object\]/);
    expect(rendered.text).not.toMatch(/undefined|NaN|\[object Object\]/);
  });
});

it("escapes user-provided text in HTML", async () => {
  const rendered = await renderEmail({
    ...base,
    name: "<script>alert(1)</script>",
    template: "verify-email",
    url: "https://orrery.test/verify",
  });
  expect(rendered.html).not.toContain("<script>alert(1)</script>");
  expect(rendered.html).toContain("&lt;script&gt;");
});
