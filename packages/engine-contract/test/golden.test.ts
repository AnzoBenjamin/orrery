import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import {
  jobSubmissionResponse,
  probeRequest,
  probeResponse,
  reconstructJobRequest,
} from "../src/index.ts";

// The same golden files are parsed by the engine's generated Pydantic models
// (services/engine/tests/test_contract.py), so both sides provably agree on the wire format.
const golden = (name: string) =>
  JSON.parse(
    readFileSync(
      join(import.meta.dirname, "../../../fixtures/golden/engine-contract", name),
      "utf8",
    ),
  ) as unknown;

describe("engine contract", () => {
  it("accepts the golden messages", () => {
    expect(probeRequest.parse(golden("probe-request.json"))).toMatchObject({ maxBytes: 1e9 });
    expect(probeResponse.parse(golden("probe-accepted.json"))).toMatchObject({
      outcome: "accepted",
    });
    expect(probeResponse.parse(golden("probe-rejected.json"))).toMatchObject({ code: "not_video" });
    expect(reconstructJobRequest.parse(golden("reconstruct-job-request.json"))).toMatchObject({
      kind: "reconstruct",
    });
    expect(jobSubmissionResponse.parse(golden("reconstruct-job-rejected.json"))).toMatchObject({
      accepted: false,
      error: { code: "capability_unavailable" },
    });
  });

  it("rejects unknown fields and out-of-range values", () => {
    const accepted = golden("probe-accepted.json") as Record<string, unknown>;
    expect(probeResponse.safeParse({ ...accepted, extra: 1 }).success).toBe(false);
    expect(probeResponse.safeParse({ ...accepted, rotationQuarterTurns: 4 }).success).toBe(false);
    expect(probeResponse.safeParse({ ...accepted, outcome: "maybe" }).success).toBe(false);
  });
});
