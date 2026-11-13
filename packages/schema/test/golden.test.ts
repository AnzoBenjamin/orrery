/**
 * Golden mechanism files (requirements 2.2 to 2.4), shared with the Rust and Python suites.
 * Property 7: parse → serialize → parse is the identity. Property 10: graphs with dangling
 * references, duplicate ids, self-joints, or two grounds fail validation.
 */
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { bodyKindSchema, followerTypeSchema, jointSchema, mechanismSchema } from "../src/index.ts";

const dir = join(import.meta.dirname, "../../../fixtures/golden/mechanism");
const read = (path: string): unknown => JSON.parse(readFileSync(path, "utf8"));
const golden = readdirSync(dir)
  .filter((f) => f.endsWith(".json"))
  .map((f) => [f, read(join(dir, f))] as const);

/** Each invalid file and the rule it breaks. */
const invalid: Record<string, RegExp> = {
  "dangling-body.json": /references non-existent body missing-body/,
  "dangling-point.json": /references non-existent point missing-point/,
  "dangling-driver-joint.json": /references non-existent joint missing-joint/,
  "dangling-plane.json": /references non-existent plane missing-plane/,
  "duplicate-body-id.json": /Duplicate body IDs/,
  "duplicate-joint-id.json": /Duplicate joint IDs/,
  "self-joint.json": /connects body coupler to itself/,
  "two-grounds.json": /exactly one ground body, found 2/,
};

describe("golden mechanisms", () => {
  it.each(golden)("%s parses, and parse → serialize → parse is the identity", (_, document) => {
    const parsed = mechanismSchema.parse(document);
    // Nothing in the file is dropped or changed by parsing.
    expect(parsed).toEqual(document);
    const again = mechanismSchema.parse(JSON.parse(JSON.stringify(parsed)));
    expect(again).toEqual(parsed);
  });

  it("cover every body kind, joint kind, follower, slot curve, and driver profile", () => {
    const mechanisms = golden.map(([, d]) => mechanismSchema.parse(d));
    const bodies = new Set(mechanisms.flatMap((m) => m.bodies.map((b) => b.kind)));
    const joints = mechanisms.flatMap((m) => m.joints);
    const kinds = new Set(joints.map((j) => j.kind));
    const followers = new Set(
      joints.flatMap((j) => (j.kind === "cam_follower" ? [j.follower] : [])),
    );
    const slots = new Set(joints.flatMap((j) => (j.kind === "pin_in_slot" ? [j.slot.type] : [])));
    const profiles = new Set(mechanisms.flatMap((m) => m.drivers.map((d) => d.profile.type)));
    const gears = joints.flatMap((j) => (j.kind === "gear_mesh" ? [Math.sign(j.ratio)] : []));
    const belts = new Set(joints.flatMap((j) => (j.kind === "belt" ? [j.crossed] : [])));

    expect([...bodies].sort()).toEqual([...bodyKindSchema.options].sort());
    expect([...kinds].sort()).toEqual(jointSchema.options.map((o) => o.shape.kind.value).sort());
    expect([...followers].sort()).toEqual([...followerTypeSchema.options].sort());
    expect([...slots].sort()).toEqual(["circular_arc", "cubic_bspline", "line_segment"]);
    expect([...profiles].sort()).toEqual(["constant_rate", "samples"]);
    // External (negative ratio) and internal (positive) meshes, open and crossed belts.
    expect(new Set(gears)).toEqual(new Set([-1, 1]));
    expect(belts).toEqual(new Set([false, true]));
    // A spatial mechanism and a mechanism with two planar subsystems.
    expect(mechanisms.some((m) => m.bodies.every((b) => b.planeId === null))).toBe(true);
    expect(mechanisms.some((m) => m.planes.length >= 2)).toBe(true);
  });
});

describe("invalid mechanisms", () => {
  const files = readdirSync(join(dir, "invalid")).filter((f) => f.endsWith(".json"));

  it("has an expected failure for every invalid file", () => {
    expect(files.sort()).toEqual(Object.keys(invalid).sort());
  });

  it.each(files)("%s is rejected for the rule it breaks", (file) => {
    const result = mechanismSchema.safeParse(read(join(dir, "invalid", file)));
    expect(result.success).toBe(false);
    const messages = result.error?.issues.map((i) => i.message).join("\n") ?? "";
    expect(messages).toMatch(invalid[file] ?? /never/);
  });
});
