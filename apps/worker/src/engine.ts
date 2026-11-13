import { type ProbeRequest, type ProbeResponse, probeResponse } from "@orrery/engine-contract";

export type { ProbeResponse };

/** The engine could not do the work now; the job should be retried. */
export class EngineUnavailableError extends Error {
  constructor(message: string, options?: { cause: unknown }) {
    super(message, options);
    this.name = "EngineUnavailableError";
  }
}

export interface EngineClient {
  probe(input: ProbeRequest, signal: AbortSignal): Promise<ProbeResponse>;
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
