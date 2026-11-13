import { z } from "zod";

/**
 * POST /v1/probe: the worker asks the engine what an uploaded file really is. The engine reads
 * the file's content, never its name or declared type (platform-foundation requirement 6.3).
 */
export const probeRequest = z
  .object({
    /** Presigned GET URL of the uploaded object, on an allowed object-store origin. */
    sourceUrl: z.string().min(1).max(8192),
    /** Stop downloading and reject past this many bytes. */
    maxBytes: z.number().int().positive().max(2_000_000_000),
    /** Reject clips longer than this. */
    maxDurationS: z.number().positive().max(3600),
  })
  .strict()
  .meta({ id: "ProbeRequest", title: "ProbeRequest" });

export const probeAccepted = z
  .object({
    outcome: z.literal("accepted"),
    /** Lowercase hex SHA-256 of the downloaded bytes. */
    sha256: z.string().regex(/^[0-9a-f]{64}$/),
    byteSize: z.number().int().nonnegative(),
    durationS: z.number().positive(),
    width: z.number().int().positive(),
    height: z.number().int().positive(),
    fpsNominal: z.number().positive(),
    isVfr: z.boolean(),
    codec: z.string().min(1).max(40),
    /** Display rotation in counter-clockwise quarter turns. */
    rotationQuarterTurns: z.literal([0, 1, 2, 3]),
  })
  .strict()
  .meta({ id: "ProbeAccepted", title: "ProbeAccepted" });

export const probeRejected = z
  .object({
    outcome: z.literal("rejected"),
    code: z.enum([
      "too_large",
      "too_long",
      "not_video",
      "unsupported_codec",
      "unsupported_container",
      "empty",
    ]),
    /** What happened and what to do next, shown to the user as written. */
    reason: z.string().min(1).max(500),
  })
  .strict()
  .meta({ id: "ProbeRejected", title: "ProbeRejected" });

export const probeResponse = z
  .discriminatedUnion("outcome", [probeAccepted, probeRejected])
  .meta({ id: "ProbeResponse", title: "ProbeResponse" });

export type ProbeRequest = z.input<typeof probeRequest>;
export type ProbeResponse = z.output<typeof probeResponse>;
