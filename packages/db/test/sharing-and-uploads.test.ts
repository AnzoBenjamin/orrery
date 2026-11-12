import { describe, expect, it } from "vitest";
import {
  completeUploadSession,
  createFootage,
  createShareLink,
  createSpecimen,
  createUploadSession,
  deleteUploadSession,
  findOpenUploadSession,
  listExpiredUploadSessions,
  listShareLinks,
  newId,
  resolveShareLink,
  revokeShareLink,
} from "../src/index.ts";
import { insertUser, useTestDatabase } from "./support.ts";

const database = useTestDatabase();
const hour = 3_600_000;
const hash = (c: string) => c.repeat(64);

describe("share links", () => {
  it("resolves active links only, and records last use", async () => {
    const owner = await insertUser(database());
    const s = await createSpecimen(database().db, { ownerId: owner.id, title: "Loom" });
    const now = new Date();
    const active = await createShareLink(database().db, {
      specimenId: s.id,
      tokenHash: hash("1"),
      createdBy: owner.id,
    });
    await createShareLink(database().db, {
      specimenId: s.id,
      tokenHash: hash("2"),
      createdBy: owner.id,
      expiresAt: new Date(now.getTime() - hour),
    });

    const resolved = await resolveShareLink(database().db, hash("1"), now);
    expect(resolved?.id).toBe(active.id);
    expect(resolved?.lastUsedAt?.getTime()).toBe(now.getTime());
    expect(await resolveShareLink(database().db, hash("2"), now)).toBeUndefined();
    expect(await resolveShareLink(database().db, hash("3"), now)).toBeUndefined();

    expect(await revokeShareLink(database().db, { id: active.id, specimenId: newId() })).toBe(
      undefined,
    );
    expect(
      (await revokeShareLink(database().db, { id: active.id, specimenId: s.id }))?.revokedAt,
    ).toBeInstanceOf(Date);
    expect(await resolveShareLink(database().db, hash("1"), now)).toBeUndefined();
    expect(await listShareLinks(database().db, s.id)).toHaveLength(2);
  });
});

describe("upload sessions", () => {
  it("finds open sessions, completes them, and lists expired ones for reaping", async () => {
    const owner = await insertUser(database());
    const s = await createSpecimen(database().db, { ownerId: owner.id, title: "Toy" });
    const footageIds = [newId(), newId()];
    for (const id of footageIds) {
      await createFootage(database().db, {
        id,
        specimenId: s.id,
        role: "reference",
        objectKey: `k/${id}`,
        originalFilename: "t.mp4",
        byteSize: 50_000_000,
      });
    }
    const now = new Date();
    const open = await createUploadSession(database().db, {
      footageId: footageIds[0] as string,
      s3UploadId: "upload-open",
      partSize: 8 * 1024 * 1024,
      expiresAt: new Date(now.getTime() + 24 * hour),
    });
    const stale = await createUploadSession(database().db, {
      footageId: footageIds[1] as string,
      s3UploadId: "upload-stale",
      partSize: 8 * 1024 * 1024,
      expiresAt: new Date(now.getTime() - hour),
    });

    expect((await findOpenUploadSession(database().db, open.footageId, now))?.id).toBe(open.id);
    expect(await findOpenUploadSession(database().db, stale.footageId, now)).toBeUndefined();
    const expired = await listExpiredUploadSessions(database().db, now, 10);
    expect(expired.map((x) => x.id)).toContain(stale.id);
    expect(expired.map((x) => x.id)).not.toContain(open.id);

    expect((await completeUploadSession(database().db, open.id))?.completedAt).toBeInstanceOf(Date);
    expect(await completeUploadSession(database().db, open.id)).toBeUndefined();
    expect(await findOpenUploadSession(database().db, open.footageId, now)).toBeUndefined();
    expect(await deleteUploadSession(database().db, stale.id)).toBe(true);
  });
});
