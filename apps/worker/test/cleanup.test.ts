import { randomBytes } from "node:crypto";
import {
  countPendingDeletions,
  createFootage,
  createSpecimen,
  type Db,
  enqueueObjectDeletions,
  findFootageById,
  markFootageProbing,
  newId,
  schema,
} from "@orrery/db";
import { createTestDatabase, startTestPostgres, type TestPostgres } from "@orrery/db/testing";
import { footageObjectKey, Storage } from "@orrery/storage";
import { startTestGarage, type TestGarage } from "@orrery/storage/testing";
import { eq, inArray } from "drizzle-orm";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { objectsDeleteHandler } from "../src/handlers/objects-delete.ts";
import { uploadsReapHandler } from "../src/handlers/uploads-reap.ts";
import { createLogger } from "../src/logger.ts";

let postgres: TestPostgres;
let garage: TestGarage;
let storage: Storage;
let db: Db;
let closeDb: () => Promise<void>;
let ownerId: string;
let specimenId: string;
const log = createLogger("silent");

async function put(key: string, body: Buffer) {
  const uploadId = await storage.createMultipartUpload(key, "video/mp4");
  const response = await fetch(await storage.presignUploadPart(key, uploadId, 1, 60), {
    method: "PUT",
    body: new Uint8Array(body),
  });
  await storage.completeMultipartUpload(key, uploadId, [
    { partNumber: 1, etag: response.headers.get("etag") ?? "" },
  ]);
}

function key() {
  return footageObjectKey({ userId: ownerId, specimenId, footageId: newId(), filename: "a.mp4" });
}

async function footage(byteSize: number) {
  const id = newId();
  const objectKey = footageObjectKey({
    userId: ownerId,
    specimenId,
    footageId: id,
    filename: "a.mp4",
  });
  await createFootage(db, {
    id,
    specimenId,
    role: "reference",
    objectKey,
    originalFilename: "a.mp4",
    byteSize,
  });
  return { id, objectKey };
}

beforeAll(async () => {
  [postgres, garage] = await Promise.all([startTestPostgres(), startTestGarage()]);
  const database = await createTestDatabase(postgres.adminUrl);
  db = database.db;
  closeDb = database.close;
  storage = new Storage(garage.config);
  const [user] = await db
    .insert(schema.user)
    .values({ name: "Reaper", email: `reap-${Date.now()}@orrery.test` })
    .returning();
  if (!user) throw new Error("no user");
  ownerId = user.id;
  specimenId = (await createSpecimen(db, { ownerId, title: "Loom" })).id;
});

afterAll(async () => {
  storage?.destroy();
  await closeDb?.();
  await Promise.all([postgres?.stop(), garage?.stop()]);
});

describe("objects.delete", () => {
  it("deletes queued objects and their unfinished uploads, and records completion", async () => {
    const stored = key();
    await put(stored, randomBytes(64));
    const partial = key();
    await storage.createMultipartUpload(partial, "video/mp4");
    const rows = await enqueueObjectDeletions(db, [stored, partial, key()]);

    await objectsDeleteHandler({ db, storage, log })();

    expect(await storage.objectSize(stored)).toBeNull();
    expect(await storage.listMultipartUploads(partial)).toEqual([]);
    const done = await db
      .select()
      .from(schema.objectDeletion)
      .where(
        inArray(
          schema.objectDeletion.id,
          rows.map((r) => r.id),
        ),
      );
    expect(done.every((r) => r.completedAt !== null)).toBe(true);
  });

  it("keeps failed deletions pending with the error, and retries them on the next run", async () => {
    const [row] = await enqueueObjectDeletions(db, [key()]);
    if (!row) throw new Error("no row");
    const broken = new Storage({ ...garage.config, bucket: "no-such-bucket" });
    await objectsDeleteHandler({ db, storage: broken, log })();
    broken.destroy();
    const [failed] = await db
      .select()
      .from(schema.objectDeletion)
      .where(eq(schema.objectDeletion.id, row.id));
    expect(failed).toMatchObject({ attempts: 1, completedAt: null });
    expect(failed?.lastError).toBeTruthy();

    await objectsDeleteHandler({ db, storage, log })();
    const [retried] = await db
      .select()
      .from(schema.objectDeletion)
      .where(eq(schema.objectDeletion.id, row.id));
    expect(retried?.completedAt).not.toBeNull();
    expect(await countPendingDeletions(db)).toBe(0);
  });
});

describe("uploads.reap", () => {
  it("finishes assembled uploads, removes abandoned ones, aborts orphans, and requeues stalls", async () => {
    const body = randomBytes(256);
    const assembled = await footage(body.length);
    await put(assembled.objectKey, body);
    const abandoned = await footage(1000);
    await storage.createMultipartUpload(abandoned.objectKey, "video/mp4");
    const orphan = key();
    await storage.createMultipartUpload(orphan, "video/mp4");
    const stalled = await footage(10);
    await markFootageProbing(db, stalled.id);

    const queued: string[] = [];
    const later = new Date(Date.now() + 25 * 3600 * 1000);
    await uploadsReapHandler({
      db,
      storage,
      enqueue: async (id) => {
        queued.push(id);
      },
      log,
      now: () => later,
    })();

    expect((await findFootageById(db, assembled.id))?.status).toBe("probing");
    expect(await findFootageById(db, abandoned.id)).toBeUndefined();
    expect(await storage.listMultipartUploads(orphan)).toEqual([]);
    expect(queued.sort()).toEqual([assembled.id, stalled.id].sort());
    expect(await countPendingDeletions(db)).toBe(1);

    // Nothing is touched before its time.
    const fresh = await footage(10);
    queued.length = 0;
    await uploadsReapHandler({ db, storage, enqueue: async (id) => void queued.push(id), log })();
    expect((await findFootageById(db, fresh.id))?.status).toBe("uploading");
    expect(queued).toEqual([]);
  });
});
