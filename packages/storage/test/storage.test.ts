import { randomBytes, randomUUID } from "node:crypto";
import fc from "fast-check";
import { afterAll, describe, expect, inject, it } from "vitest";
import {
  footageObjectKey,
  MAX_FOOTAGE_BYTES,
  MAX_PARTS,
  MIN_PART_BYTES,
  partCount,
  partSizeFor,
  Storage,
  storedExtension,
} from "../src/index.ts";

const storage = new Storage(inject("garage"));
afterAll(() => storage.destroy());

const MIB = 1024 * 1024;

function key() {
  return footageObjectKey({
    userId: randomUUID(),
    specimenId: randomUUID(),
    footageId: randomUUID(),
    filename: "clip.MP4",
  });
}

/** Uploads one part the way a browser does: a plain PUT to the presigned URL. */
async function putPart(url: string, body: Uint8Array): Promise<string> {
  const response = await fetch(url, { method: "PUT", body });
  expect(response.status).toBe(200);
  const etag = response.headers.get("etag");
  if (!etag) throw new Error("part upload returned no ETag");
  return etag;
}

describe("object keys", () => {
  it("scope keys by user and specimen and never use the user's file name", () => {
    const userId = randomUUID();
    const specimenId = randomUUID();
    const footageId = randomUUID();
    expect(footageObjectKey({ userId, specimenId, footageId, filename: "../../etc/passwd" })).toBe(
      `users/${userId}/specimens/${specimenId}/footage/${footageId}.bin`,
    );
    expect(storedExtension("Treadle run.MOV")).toBe("mov");
    expect(storedExtension("noextension")).toBe("bin");
    expect(() =>
      footageObjectKey({ userId: "x/..", specimenId, footageId, filename: "a.mp4" }),
    ).toThrow();
  });
});

describe("part sizes", () => {
  it("stay within S3's limits for every allowed file size", () => {
    fc.assert(
      fc.property(fc.integer({ min: 0, max: MAX_FOOTAGE_BYTES * 50 }), (bytes) => {
        const size = partSizeFor(bytes);
        expect(size).toBeGreaterThanOrEqual(MIN_PART_BYTES);
        expect(size % MIB).toBe(0);
        expect(partCount(bytes, size)).toBeLessThanOrEqual(MAX_PARTS);
        expect(partCount(bytes, size) * size).toBeGreaterThanOrEqual(bytes);
      }),
    );
  });
});

describe("Garage storage", () => {
  it("uploads in parts through presigned URLs, lists them for resuming, and completes", async () => {
    const k = key();
    const uploadId = await storage.createMultipartUpload(k, "video/mp4");
    const first = randomBytes(5 * MIB);
    const second = randomBytes(1234);

    const etag1 = await putPart(await storage.presignUploadPart(k, uploadId, 1, 60), first);
    expect(await storage.listParts(k, uploadId)).toEqual([
      { partNumber: 1, etag: etag1, size: first.length },
    ]);
    const etag2 = await putPart(await storage.presignUploadPart(k, uploadId, 2, 60), second);

    const pending = await storage.listMultipartUploads(k);
    expect(pending.map((u) => u.uploadId)).toContain(uploadId);

    await storage.completeMultipartUpload(k, uploadId, [
      { partNumber: 2, etag: etag2 },
      { partNumber: 1, etag: etag1 },
    ]);
    expect(await storage.objectSize(k)).toBe(first.length + second.length);
    expect(await storage.listMultipartUploads(k)).toEqual([]);

    const read = await fetch(await storage.presignGet(k, 60));
    expect(read.status).toBe(200);
    expect(Buffer.from(await read.arrayBuffer()).subarray(0, 64)).toEqual(first.subarray(0, 64));
  });

  it("refuses reads and writes without a valid signature", async () => {
    const k = key();
    const uploadId = await storage.createMultipartUpload(k, "video/mp4");
    const url = new URL(await storage.presignUploadPart(k, uploadId, 1, 60));
    url.searchParams.set("partNumber", "2");
    const tampered = await fetch(url, { method: "PUT", body: new Uint8Array(10) });
    expect(tampered.status).toBe(403);
    const cfg = inject("garage");
    const anonymous = await fetch(`${cfg.endpoint}/${cfg.bucket}/${k}`);
    expect(anonymous.status).toBeGreaterThanOrEqual(400);
    await storage.abortMultipartUpload(k, uploadId);
  });

  it("deleting a key aborts its unfinished uploads and is idempotent", async () => {
    const k = key();
    const uploadId = await storage.createMultipartUpload(k, "video/mp4");
    await putPart(await storage.presignUploadPart(k, uploadId, 1, 60), randomBytes(100));

    await storage.deleteObject(k);
    expect(await storage.listMultipartUploads(k)).toEqual([]);
    expect(await storage.listParts(k, uploadId)).toBeNull();
    await storage.deleteObject(k);
    await storage.abortMultipartUpload(k, uploadId);
    expect(await storage.objectSize(k)).toBeNull();
  });

  it("caps presigned URL lifetimes at 15 minutes", async () => {
    const url = new URL(await storage.presignGet(key(), 24 * 3600));
    expect(url.searchParams.get("X-Amz-Expires")).toBe("900");
  });
});
