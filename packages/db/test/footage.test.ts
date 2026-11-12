import { describe, expect, it } from "vitest";
import {
  createFootage,
  createSpecimen,
  deleteFootage,
  findFootage,
  listFootageForSpecimen,
  markFootageProbing,
  markFootageReady,
  markFootageRejected,
  newId,
  type ProbeResult,
  storageBytesForOwner,
} from "../src/index.ts";
import { insertUser, useTestDatabase } from "./support.ts";

const database = useTestDatabase();

const probe: ProbeResult = {
  sha256: "a".repeat(64),
  byteSize: 1_048_576,
  durationS: 12.5,
  width: 1920,
  height: 1080,
  fpsNominal: 29.97,
  isVfr: false,
  codec: "h264",
  rotationQuarterTurns: 1,
};

async function setup() {
  const owner = await insertUser(database());
  const s = await createSpecimen(database().db, { ownerId: owner.id, title: "Clock" });
  const f = await createFootage(database().db, {
    id: newId(),
    specimenId: s.id,
    role: "reference",
    objectKey: `users/${owner.id}/specimens/${s.id}/footage/${newId()}.mp4`,
    originalFilename: "clock.mp4",
    byteSize: 1_000_000,
  });
  return { owner, s, f };
}

describe("footage", () => {
  it("moves through uploading, probing, and ready, and refuses skipped steps", async () => {
    const { s, f } = await setup();
    expect(f.status).toBe("uploading");
    expect(await markFootageReady(database().db, f.id, probe)).toBeUndefined();
    expect((await markFootageProbing(database().db, f.id))?.status).toBe("probing");
    expect(await markFootageProbing(database().db, f.id)).toBeUndefined();
    const ready = await markFootageReady(database().db, f.id, probe);
    expect(ready).toMatchObject({ status: "ready", durationS: 12.5, rotationQuarterTurns: 1 });
    expect(await markFootageRejected(database().db, f.id, "late")).toBeUndefined();
    expect(await listFootageForSpecimen(database().db, s.id)).toHaveLength(1);
  });

  it("records a rejection reason", async () => {
    const { f } = await setup();
    const rejected = await markFootageRejected(
      database().db,
      f.id,
      "This file is not a video we can read (container: zip).",
    );
    expect(rejected).toMatchObject({ status: "rejected" });
    expect(rejected?.rejectionReason).toContain("container: zip");
  });

  it("scopes lookups and deletion to the specimen", async () => {
    const { f, s } = await setup();
    const other = await setup();
    expect(await findFootage(database().db, { id: f.id, specimenId: other.s.id })).toBeUndefined();
    expect(await deleteFootage(database().db, { id: f.id, specimenId: other.s.id })).toBe(false);
    expect(await deleteFootage(database().db, { id: f.id, specimenId: s.id })).toBe(true);
    expect(await findFootage(database().db, { id: f.id, specimenId: s.id })).toBeUndefined();
  });

  it("sums stored bytes per owner across specimens", async () => {
    const { owner } = await setup();
    const second = await createSpecimen(database().db, { ownerId: owner.id, title: "Second" });
    await createFootage(database().db, {
      id: newId(),
      specimenId: second.id,
      role: "broken",
      objectKey: `k/${newId()}`,
      originalFilename: "b.mp4",
      byteSize: 3_000_000_000,
    });
    expect(await storageBytesForOwner(database().db, owner.id)).toBe(3_001_000_000);
    expect(await storageBytesForOwner(database().db, newId())).toBe(0);
  });
});
