import { z } from "zod";
import { defineQueue } from "./queue.ts";

const recipient = z.object({
  to: z.email(),
  /** The recipient's display name, used in the greeting. */
  name: z.string().min(1).max(200),
});

/** Every email Orrery sends. Each variant maps to one React Email template in packages/email. */
export const emailMessage = z.discriminatedUnion("template", [
  recipient.extend({ template: z.literal("verify-email"), url: z.url() }),
  recipient.extend({ template: z.literal("reset-password"), url: z.url() }),
  recipient.extend({
    template: z.literal("sign-in-alert"),
    at: z.iso.datetime(),
    /** Browser and operating system summary, for example "Firefox on Linux". */
    device: z.string().min(1).max(200),
    /** First two octets of IPv4 or first three hextets of IPv6, never the full address. */
    ipPrefix: z.string().min(1).max(64),
    sessionsUrl: z.url(),
  }),
  recipient.extend({
    template: z.literal("analysis-complete"),
    specimenTitle: z.string().min(1).max(200),
    url: z.url(),
    preferencesUrl: z.url(),
  }),
]);

export type EmailMessage = z.output<typeof emailMessage>;

export const emailSend = defineQueue({
  name: "email.send",
  schema: z.object({
    message: emailMessage,
    /** Caller-chosen key that suppresses duplicate sends of the same message. */
    idempotencyKey: z.string().min(1).max(200).optional(),
  }),
  retryLimit: 8,
  retryDelaySeconds: 30,
  retryBackoff: true,
  expireInSeconds: 120,
  idempotencyKey: (p) => p.idempotencyKey,
});

/** Every queue the worker serves. A queue is listed here only once its handler exists. */
export const allQueues = [emailSend] as const;
