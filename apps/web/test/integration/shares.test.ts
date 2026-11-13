import { markFootageReady, schema } from "@orrery/db";
import { eq } from "drizzle-orm";
import { describe, expect, it } from "vitest";
import { anonymous } from "../../src/server/actor.ts";
import { invoke } from "../../src/server/operations/define.ts";
import { footageUploadCreate } from "../../src/server/operations/footage.ts";
import {
  hashShareToken,
  shareCreate,
  shareList,
  shareOpen,
  sharePlayback,
  shareRevoke,
} from "../../src/server/operations/shares.ts";
import { specimenCreate } from "../../src/server/operations/specimens.ts";
import { limitPolicies } from "../../src/server/rate-limits.ts";
import { userActor, withTestDatabase } from "./support.ts";

const database = withTestDatabase();

async function ok<T>(
  promise: Promise<{ ok: true; value: T } | { ok: false; error: { message: string } }>,
) {
  const result = await promise;
  if (!result.ok) throw new Error(result.error.message);
  return result.value;
}

const visitor = (ip: string) => ({ request: { ip } });

async function specimenWithFootage(title: string) {
  const owner = await userActor(database());
  const specimen = await ok(invoke(database().deps, specimenCreate, owner, { title }));
  const make = async (filename: string) =>
    ok(
      invoke(database().deps, footageUploadCreate, owner, {
        specimenId: specimen.id,
        role: "reference",
        filename,
        byteSize: 100,
      }),
    );
  const ready = await make("ready.mp4");
  await database()
    .db.update(schema.footage)
    .set({ status: "probing" })
    .where(eq(schema.footage.id, ready.footageId));
  await markFootageReady(database().db, ready.footageId, {
    sha256: "1".repeat(64),
    byteSize: 100,
    durationS: 3,
    width: 640,
    height: 480,
    fpsNominal: 30,
    isVfr: false,
    codec: "h264",
    rotationQuarterTurns: 0,
  });
  await make("still-uploading.mp4");
  return { owner, specimen, readyFootageId: ready.footageId };
}

describe("share links", () => {
  it("shows a specimen and its checked footage to anyone with the token, read only", async () => {
    const { owner, specimen, readyFootageId } = await specimenWithFootage("Shared orrery");
    const created = await ok(
      invoke(database().deps, shareCreate, owner, { specimenId: specimen.id, expiresInDays: 7 }),
    );
    expect(created.token).toMatch(/^[A-Za-z0-9_-]{43}$/);
    expect(created.link).toMatchObject({ active: true, revokedAt: null });

    const [stored] = await database()
      .db.select()
      .from(schema.shareLink)
      .where(eq(schema.shareLink.id, created.link.id));
    expect(stored?.tokenHash).toBe(hashShareToken(created.token));
    expect(JSON.stringify(stored)).not.toContain(created.token);

    const opened = await ok(
      invoke(database().deps, shareOpen, anonymous, { token: created.token }, visitor("192.0.2.1")),
    );
    expect(opened.title).toBe("Shared orrery");
    expect(opened.footage.map((f) => f.id)).toEqual([readyFootageId]);
    expect(JSON.stringify(opened)).not.toContain(owner.userId);

    const playback = await ok(
      invoke(
        database().deps,
        sharePlayback,
        anonymous,
        { token: created.token, footageId: readyFootageId },
        visitor("192.0.2.1"),
      ),
    );
    expect(playback.url).toContain(specimen.id);

    const listed = await ok(invoke(database().deps, shareList, owner, { specimenId: specimen.id }));
    expect(listed[0]?.lastUsedAt).not.toBeNull();
  });

  it("stops working once revoked or expired", async () => {
    const { owner, specimen } = await specimenWithFootage("Revoked loom");
    const a = await ok(invoke(database().deps, shareCreate, owner, { specimenId: specimen.id }));
    const b = await ok(invoke(database().deps, shareCreate, owner, { specimenId: specimen.id }));

    const revoked = await ok(
      invoke(database().deps, shareRevoke, owner, { shareLinkId: a.link.id }),
    );
    expect(revoked.active).toBe(false);
    expect(
      await invoke(database().deps, shareOpen, anonymous, { token: a.token }, visitor("192.0.2.2")),
    ).toMatchObject({ ok: false, error: { kind: "NotFound" } });

    await database()
      .db.update(schema.shareLink)
      .set({ expiresAt: new Date(Date.now() - 1000) })
      .where(eq(schema.shareLink.id, b.link.id));
    expect(
      await invoke(database().deps, shareOpen, anonymous, { token: b.token }, visitor("192.0.2.2")),
    ).toMatchObject({ ok: false, error: { kind: "NotFound" } });
  });

  it("a token for one specimen cannot play another specimen's footage", async () => {
    const first = await specimenWithFootage("First");
    const second = await specimenWithFootage("Second");
    const link = await ok(
      invoke(database().deps, shareCreate, first.owner, { specimenId: first.specimen.id }),
    );
    expect(
      await invoke(
        database().deps,
        sharePlayback,
        anonymous,
        { token: link.token, footageId: second.readyFootageId },
        visitor("192.0.2.3"),
      ),
    ).toMatchObject({ ok: false, error: { kind: "NotFound" } });
  });

  it("limits how often one address can open links", async () => {
    const { owner, specimen } = await specimenWithFootage("Popular");
    const link = await ok(invoke(database().deps, shareCreate, owner, { specimenId: specimen.id }));
    const { points } = limitPolicies["share-access"];
    for (let i = 0; i < points; i += 1) {
      await ok(
        invoke(
          database().deps,
          shareOpen,
          anonymous,
          { token: link.token },
          visitor("198.51.100.9"),
        ),
      );
    }
    expect(
      await invoke(
        database().deps,
        shareOpen,
        anonymous,
        { token: link.token },
        visitor("198.51.100.9"),
      ),
    ).toMatchObject({ ok: false, error: { kind: "RateLimited", message: /Wait \d+ second/ } });
    // Another address is unaffected.
    await ok(
      invoke(
        database().deps,
        shareOpen,
        anonymous,
        { token: link.token },
        visitor("198.51.100.10"),
      ),
    );
  });
});
