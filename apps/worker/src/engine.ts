import { z } from "zod";

/**
 * The engine's probe response. The engine contract package (platform-foundation task 7.5) will
 * generate this from one schema for both sides; until then this mirrors
 * services/engine/src/orrery_engine/app.py and validates every response.
 */
const probeResponse = z.discriminatedUnion("outcome", [
  z.object({
    outcome: z.literal("accepted"),
    sha256: z.string().regex(/^[0-9a-f]{64}$/),
    byteSize: z.number().int().nonnegative(),
    durationS: z.number().positive(),
    width: z.number().int().positive(),
    height: z.number().int().positive(),
    fpsNominal: z.number().positive(),
    isVfr: z.boolean(),
    codec: z.string().min(1).max(40),
    rotationQuarterTurns: z.union([z.literal(0), z.literal(1), z.literal(2), z.literal(3)]),
  }),
  z.object({
    outcome: z.literal("rejected"),
    code: z.string().min(1).max(40),
    reason: z.string().min(1).max(500),
  }),
]);

export type ProbeResponse = z.output<typeof probeResponse>;

/** The engine could not do the work now; the job should be retried. */
export class EngineUnavailableError extends Error {
  constructor(message: string, options?: { cause: unknown }) {
    super(message, options);
    this.name = "EngineUnavailableError";
  }
}

export interface EngineClient {
  probe(
    input: { sourceUrl: string; maxBytes: number; maxDurationS: number },
    signal: AbortSignal,
  ): Promise<ProbeResponse>;
}

export function createEngineClient(config: { url: string; token: string }): EngineClient {
  return {
    async probe(input, signal) {
      let response: Response;
      try {
        response = await fetch(new URL("/v1/probe", config.url), {
          method: "POST",
          headers: {
            authorization: `Bearer ${config.token}`,
            "content-type": "application/json",
          },
          body: JSON.stringify(input),
          signal,
        });
      } catch (error) {
        throw new EngineUnavailableError("engine unreachable", { cause: error });
      }
      if (!response.ok) {
        throw new EngineUnavailableError(`engine answered ${response.status}`);
      }
      return probeResponse.parse(await response.json());
    },
  };
}
