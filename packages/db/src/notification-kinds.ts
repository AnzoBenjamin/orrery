import { z } from "zod";

/**
 * Every notification the system creates. Payloads are validated on write and again on read, so
 * the tray never renders a row it does not understand.
 */
export const notificationBody = z.discriminatedUnion("kind", [
  z.object({
    kind: z.literal("footage.ready"),
    payload: z.object({
      specimenId: z.uuid(),
      specimenTitle: z.string().min(1).max(200),
      footageId: z.uuid(),
      filename: z.string().min(1).max(255),
    }),
  }),
  z.object({
    kind: z.literal("footage.rejected"),
    payload: z.object({
      specimenId: z.uuid(),
      specimenTitle: z.string().min(1).max(200),
      footageId: z.uuid(),
      filename: z.string().min(1).max(255),
      reason: z.string().min(1).max(500),
    }),
  }),
]);

export type NotificationBody = z.output<typeof notificationBody>;
