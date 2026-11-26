import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import {
  analysisArtifacts,
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

  it("requires positions only for observed track samples", () => {
    const artifact = {
      format: "orrery.engine.analysis-artifacts",
      schemaVersion: 1,
      engineVersion: "test",
      tracks: [
        {
          trackId: "footage:seed-1",
          footageId: "footage",
          seedId: "seed-1",
          source: "shi_tomasi",
          samples: [
            {
              frameIndex: 0,
              xPx: 10,
              yPx: 20,
              visible: true,
              confidence: 0.9,
              status: "observed",
            },
            {
              frameIndex: 1,
              visible: false,
              confidence: 0,
              status: "occluded",
              rejectionReason: "appearance",
            },
          ],
        },
      ],
      cameraMotion: [],
      bodies: [],
      joints: [],
      parameters: [],
      diagnosis: [],
      resurrection: [],
      stageRuntimes: [],
    };
    expect(analysisArtifacts.safeParse(artifact).success).toBe(true);
    const invalid = structuredClone(artifact);
    Object.assign(invalid.tracks[0].samples[1], { xPx: 10, yPx: 20 });
    expect(analysisArtifacts.safeParse(invalid).success).toBe(false);
  });

  it("rejects unknown fields and out-of-range values", () => {
    const accepted = golden("probe-accepted.json") as Record<string, unknown>;
    expect(probeResponse.safeParse({ ...accepted, extra: 1 }).success).toBe(false);
    expect(probeResponse.safeParse({ ...accepted, rotationQuarterTurns: 4 }).success).toBe(false);
    expect(probeResponse.safeParse({ ...accepted, outcome: "maybe" }).success).toBe(false);
  });
});
