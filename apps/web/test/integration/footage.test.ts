import { randomBytes } from "node:crypto";
import { countPendingDeletions, markFootageReady, schema } from "@orrery/db";
import { footageProbe, jobIdFor } from "@orrery/jobs";
import { MAX_FOOTAGE_BYTES } from "@orrery/storage";
import { eq } from "drizzle-orm";
import { describe, expect, it } from "vitest";
import type { Actor } from "../../src/server/actor.ts";
import { type Deps, invoke } from "../../src/server/operations/define.ts";
import {
  footageDelete,
  footageList,
  footagePlayback,
  footageUploadAbort,
  footageUploadComplete,
  footageUploadCreate,
  footageUploadSign,
  footageUsage,
} from "../../src/server/operations/footage.ts";
import { specimenCreate } from "../../src/server/operations/specimens.ts";
import { TEST_QUOTA_BYTES, userActor, withTestDatabase } from "./support.ts";

const database = withTestDatabase();

async function ok<T>(
  promise: Promise<{ ok: true; value: T } | { ok: false; error: { message: string } }>,
) {
  const result = await promise;
  if (!result.ok) throw new Error(result.error.message);
  return result.value;
}

async function specimenFor(actor: Actor) {
  return ok(invoke(database().deps, specimenCreate, actor, { title: "Treadle" }));
}

type SignRequest =
  | { step: "create" }
  | { step: "part"; uploadId: string; partNumber: number }
  | { step: "list-parts" | "complete" | "abort"; uploadId: string };

async function sign(deps: Deps, actor: Actor, footageId: string, request: SignRequest) {
  return ok(invoke(deps, footageUploadSign, actor, { footageId, request }));
}

/**
 * Uploads `body` exactly as Uppy does in the browser: each S3 request is signed by the server
 * and sent straight to Garage. Returns the upload id; completes the object unless told not to.
 */
async function browserUpload(
  deps: Deps,
  actor: Actor,
  footageId: string,
  body: Buffer,
  options: { complete?: boolean } = {},
) {
  const created = await sign(deps, actor, footageId, { step: "create" });
  const xml = await (await fetch(created.url, { method: "POST" })).text();
  const uploadId = /<UploadId>([^<]+)<\/UploadId>/.exec(xml)?.[1];
  if (!uploadId) throw new Error(`no upload id in ${xml}`);
  const part = await sign(deps, actor, footageId, { step: "part", uploadId, partNumber: 1 });
  const put = await fetch(part.url, { method: "PUT", body: new Uint8Array(body) });
  expect(put.status).toBe(200);
  const etag = put.headers.get("etag") ?? "";
  if (options.complete !== false) {
    const done = await sign(deps, actor, footageId, { step: "complete", uploadId });
    const response = await fetch(done.url, {
      method: "POST",
      body: `<CompleteMultipartUpload><Part><PartNumber>1</PartNumber><ETag>${etag}</ETag></Part></CompleteMultipartUpload>`,
    });
    expect(response.status).toBe(200);
  }
  return { uploadId, etag };
}

describe("footage uploads", () => {
  it("creates, uploads, resumes from listed parts, completes, and queues the probe", async () => {
    const user = await userActor(database());
    const specimen = await specimenFor(user);
    const body = randomBytes(4096);
    const created = await ok(
      invoke(database().deps, footageUploadCreate, user, {
        specimenId: specimen.id,
        role: "broken",
        filename: "Seized bobbin.MOV",
        byteSize: body.length,
      }),
    );
    expect(created.key).toBe(
      `users/${user.userId}/specimens/${specimen.id}/footage/${created.footageId}.mov`,
    );

    const notYet = await invoke(database().deps, footageUploadComplete, user, {
      footageId: created.footageId,
    });
    expect(notYet).toMatchObject({ ok: false, error: { kind: "Conflict" } });

    const { uploadId, etag } = await browserUpload(database().deps, user, created.footageId, body, {
      complete: false,
    });
    // Resuming: the browser lists the parts S3 already holds.
    const list = await sign(database().deps, user, created.footageId, {
      step: "list-parts",
      uploadId,
    });
    expect(await (await fetch(list.url)).text()).toContain(etag.replaceAll('"', ""));
    // A second upload cannot be started over the first.
    expect(
      await invoke(database().deps, footageUploadSign, user, {
        footageId: created.footageId,
        request: { step: "create" },
      }),
    ).toMatchObject({ ok: false, error: { kind: "Conflict" } });
    // Nor can another upload id be slipped in.
    expect(
      await invoke(database().deps, footageUploadSign, user, {
        footageId: created.footageId,
        request: { step: "complete", uploadId: "forged" },
      }),
    ).toMatchObject({ ok: false, error: { kind: "Conflict" } });

    const finish = await sign(database().deps, user, created.footageId, {
      step: "complete",
      uploadId,
    });
    await fetch(finish.url, {
      method: "POST",
      body: `<CompleteMultipartUpload><Part><PartNumber>1</PartNumber><ETag>${etag}</ETag></Part></CompleteMultipartUpload>`,
    });
    const done = await ok(
      invoke(database().deps, footageUploadComplete, user, { footageId: created.footageId }),
    );
    expect(done).toMatchObject({
      status: "probing",
      role: "broken",
      filename: "Seized bobbin.MOV",
    });
    const job = await database().boss.getJobById(
      footageProbe.name,
      jobIdFor(footageProbe.name, created.footageId),
    );
    expect(job?.data).toMatchObject({ payload: { footageId: created.footageId } });

    // A retried completion after success is refused instead of re-probing.
    const again = await invoke(database().deps, footageUploadComplete, user, {
      footageId: created.footageId,
    });
    expect(again).toMatchObject({ ok: false, error: { kind: "Conflict" } });

    const listed = await ok(
      invoke(database().deps, footageList, user, { specimenId: specimen.id }),
    );
    expect(listed.map((f) => f.id)).toEqual([created.footageId]);
  });

  it("rejects an upload whose stored size differs from the declared size", async () => {
    const user = await userActor(database());
    const specimen = await specimenFor(user);
    const created = await ok(
      invoke(database().deps, footageUploadCreate, user, {
        specimenId: specimen.id,
        role: "reference",
        filename: "clip.mp4",
        byteSize: 2000,
      }),
    );
    await browserUpload(database().deps, user, created.footageId, randomBytes(1000));
    const done = await ok(
      invoke(database().deps, footageUploadComplete, user, { footageId: created.footageId }),
    );
    expect(done.status).toBe("rejected");
    expect(done.rejectionReason).toMatch(/incomplete/);
  });

  it("enforces verification, size, part range, and the storage quota", async () => {
    const user = await userActor(database());
    const specimen = await specimenFor(user);
    const unverified: Actor = { ...user, emailVerified: false };
    const base = { specimenId: specimen.id, role: "reference", filename: "a.mp4" } as const;

    expect(
      await invoke(database().deps, footageUploadCreate, unverified, { ...base, byteSize: 10 }),
    ).toMatchObject({ ok: false, error: { kind: "Forbidden" } });
    expect(
      await invoke(database().deps, footageUploadCreate, user, {
        ...base,
        byteSize: MAX_FOOTAGE_BYTES + 1,
      }),
    ).toMatchObject({
      ok: false,
      error: { kind: "Invalid", fields: { byteSize: expect.stringMatching(/1 GB/) } },
    });

    const big = await ok(
      invoke(database().deps, footageUploadCreate, user, {
        ...base,
        byteSize: TEST_QUOTA_BYTES - 100,
      }),
    );
    expect(
      await invoke(database().deps, footageUploadCreate, user, { ...base, byteSize: 200 }),
    ).toMatchObject({
      ok: false,
      error: { kind: "Conflict", message: expect.stringMatching(/storage/) },
    });
    const usage = await ok(invoke(database().deps, footageUsage, user, {}));
    expect(usage).toEqual({ usedBytes: TEST_QUOTA_BYTES - 100, quotaBytes: TEST_QUOTA_BYTES });

    const created = await sign(database().deps, user, big.footageId, { step: "create" });
    const xml = await (await fetch(created.url, { method: "POST" })).text();
    const bigUploadId = /<UploadId>([^<]+)<\/UploadId>/.exec(xml)?.[1] ?? "";
    expect(
      await invoke(database().deps, footageUploadSign, user, {
        footageId: big.footageId,
        request: { step: "part", uploadId: bigUploadId, partNumber: 10_000 },
      }),
    ).toMatchObject({ ok: false, error: { kind: "Invalid" } });
  });

  it("aborting removes the footage and the unfinished upload", async () => {
    const user = await userActor(database());
    const specimen = await specimenFor(user);
    const created = await ok(
      invoke(database().deps, footageUploadCreate, user, {
        specimenId: specimen.id,
        role: "supplementary",
        filename: "side.mp4",
        byteSize: 100,
      }),
    );
    await browserUpload(database().deps, user, created.footageId, randomBytes(100), {
      complete: false,
    });
    await ok(invoke(database().deps, footageUploadAbort, user, { footageId: created.footageId }));
    expect(await database().storage.listMultipartUploads(created.key)).toEqual([]);
    const rows = await database()
      .db.select()
      .from(schema.footage)
      .where(eq(schema.footage.id, created.footageId));
    expect(rows).toEqual([]);
  });

  it("plays only ready footage, and deleting queues the object for removal", async () => {
    const user = await userActor(database());
    const specimen = await specimenFor(user);
    const body = randomBytes(512);
    const created = await ok(
      invoke(database().deps, footageUploadCreate, user, {
        specimenId: specimen.id,
        role: "reference",
        filename: "ok.mp4",
        byteSize: body.length,
      }),
    );
    await browserUpload(database().deps, user, created.footageId, body);
    await ok(
      invoke(database().deps, footageUploadComplete, user, { footageId: created.footageId }),
    );
    expect(
      await invoke(database().deps, footagePlayback, user, { footageId: created.footageId }),
    ).toMatchObject({ ok: false, error: { kind: "Conflict" } });

    await markFootageReady(database().db, created.footageId, {
      sha256: "0".repeat(64),
      byteSize: body.length,
      durationS: 2,
      width: 640,
      height: 480,
      fpsNominal: 30,
      isVfr: false,
      codec: "h264",
      rotationQuarterTurns: 0,
    });
    const playback = await ok(
      invoke(database().deps, footagePlayback, user, { footageId: created.footageId }),
    );
    const response = await fetch(playback.url);
    expect(Buffer.from(await response.arrayBuffer())).toEqual(body);

    const pending = await countPendingDeletions(database().db);
    await ok(invoke(database().deps, footageDelete, user, { footageId: created.footageId }));
    expect(await countPendingDeletions(database().db)).toBe(pending + 1);
  });
});
