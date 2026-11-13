import { z } from "zod";

/**
 * Specimen events streamed to the browser over SSE (requirement 8). Each says what changed, not
 * the new state: the client refetches what it shows. Validated on write and on read.
 */
export const domainEventBody = z.discriminatedUnion("type", [
  z.object({
    type: z.literal("footage.changed"),
    payload: z.object({
      footageId: z.uuid(),
      status: z.enum(["uploading", "probing", "ready", "rejected", "deleted"]),
    }),
  }),
  z.object({
    type: z.literal("specimen.changed"),
    payload: z.object({}),
  }),
]);

export type DomainEventBody = z.output<typeof domainEventBody>;
