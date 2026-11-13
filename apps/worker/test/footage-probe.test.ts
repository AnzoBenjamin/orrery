import { type ChildProcess, execFileSync, spawn } from "node:child_process";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  createFootage,
  createSpecimen,
  type Db,
  findFootageById,
  markFootageProbing,
  newId,
  schema,
} from "@orrery/db";
import { createTestDatabase, startTestPostgres, type TestPostgres } from "@orrery/db/testing";
import type { JobContext } from "@orrery/jobs";
import { footageObjectKey, Storage } from "@orrery/storage";
import { startTestGarage, type TestGarage } from "@orrery/storage/testing";
import { eq } from "drizzle-orm";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { createEngineClient } from "../src/engine.ts";
import { footageProbeHandler } from "../src/handlers/footage-probe.ts";
import { createLogger } from "../src/logger.ts";

// The real engine (services/engine) on the real object store: the worker presigns a read, the
// engine downloads and inspects the file, and the worker records the verdict.

const TOKEN = "worker-engine-test-token-0123456789abcdef";
const clips = mkdtempSync(join(tmpdir(), "orrery-clips-"));

let postgres: TestPostgres;
let garage: TestGarage;
let engineProcess: ChildProcess;
let engineUrl: string;
let storage: Storage;
let db: Db;
let closeDb: () => Promise<void>;
let ownerId: string;
let specimenId: string;

function freePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const server = createServer();
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      server.close(() =>
        typeof address === "object" && address
          ? resolve(address.port)
          : reject(new Error("no port")),
      );
    });
  });
}

async function waitForHealth(url: string) {
  const deadline = Date.now() + 60_000;
  while (Date.now() < deadline) {
    try {
      if ((await fetch(`${url}/health`)).ok) return;
    } catch {
      // not listening yet
    }
    await new Promise((r) => setTimeout(r, 200));
  }
  throw new Error("engine did not become healthy");
}

function ffmpeg(...args: string[]) {
  execFileSync("ffmpeg", ["-loglevel", "error", "-y", ...args]);
}

/** Stores bytes the way browsers do: one presigned multipart part, then completion. */
async function put(key: string, body: Buffer) {
  const uploadId = await storage.createMultipartUpload(key, "application/octet-stream");
  const response = await fetch(await storage.presignUploadPart(key, uploadId, 1, 60), {
    method: "PUT",
    body: new Uint8Array(body),
  });
  await storage.completeMultipartUpload(key, uploadId, [
    { partNumber: 1, etag: response.headers.get("etag") ?? "" },
  ]);
}

async function probingFootage(body: Buffer, filename: string) {
  const id = newId();
  const objectKey = footageObjectKey({ userId: ownerId, specimenId, footageId: id, filename });
  await put(objectKey, body);
  await createFootage(db, {
    id,
    specimenId,
    role: "reference",
    objectKey,
    originalFilename: filename,
    byteSize: body.length,
  });
  await markFootageProbing(db, id);
  return id;
}

/** The kinds of the owner's notifications about one footage item. */
async function noticesFor(footageId: string) {
  const rows = await db
    .select()
    .from(schema.notification)
    .where(eq(schema.notification.userId, ownerId));
  return rows.filter((r) => r.payload.footageId === footageId).map((r) => r.kind);
}

const job = (retryCount = 0): JobContext => ({
  id: newId(),
  retryCount,
  traceparent: null,
  signal: AbortSignal.timeout(60_000),
});

beforeAll(async () => {
  [postgres, garage] = await Promise.all([startTestPostgres(), startTestGarage()]);
  const database = await createTestDatabase(postgres.adminUrl);
  db = database.db;
  closeDb = database.close;
  storage = new Storage(garage.config);

  const port = await freePort();
  engineUrl = `http://127.0.0.1:${port}`;
  engineProcess = spawn("uv", ["run", "--frozen", "python", "-m", "orrery_engine"], {
    env: {
      ...process.env,
      ENGINE_SERVICE_TOKEN: TOKEN,
      ENGINE_ALLOWED_SOURCE_ORIGINS: new URL(garage.config.endpoint).origin,
      ENGINE_PORT: String(port),
      ENGINE_WORK_DIR: clips,
      ENGINE_LOG_LEVEL: "warning",
    },
    stdio: ["ignore", "inherit", "inherit"],
  });
  await waitForHealth(engineUrl);

  const [user] = await db
    .insert(schema.user)
    .values({ name: "Probe", email: `probe-${Date.now()}@orrery.test`, emailVerified: true })
    .returning();
  if (!user) throw new Error("no user");
  ownerId = user.id;
  specimenId = (await createSpecimen(db, { ownerId, title: "Clock" })).id;

  // biome-ignore format: FFmpeg arguments read as flag and value pairs
  ffmpeg(
    "-f", "lavfi", "-i", "testsrc=size=320x240:rate=30", "-t", "2",
    "-c:v", "libx264", "-pix_fmt", "yuv420p", join(clips, "clip.mp4"),
  );
  writeFileSync(join(clips, "notes.mp4"), "not a video at all ".repeat(100));
});

afterAll(async () => {
  engineProcess?.kill("SIGTERM");
  storage?.destroy();
  await closeDb?.();
  await Promise.all([postgres?.stop(), garage?.stop()]);
});

describe("footage.probe", () => {
  const handler = () =>
    footageProbeHandler({
      db,
      storage,
      engine: createEngineClient({ url: engineUrl, token: TOKEN }),
      log: createLogger("warn"),
    });

  it("marks a real video ready with the engine's measurements", async () => {
    const body = readFileSync(join(clips, "clip.mp4"));
    const id = await probingFootage(body, "clip.mp4");
    await handler()({ footageId: id }, job());
    const footage = await findFootageById(db, id);
    expect(footage).toMatchObject({
      status: "ready",
      codec: "h264",
      width: 320,
      height: 240,
      isVfr: false,
      rotationQuarterTurns: 0,
      byteSize: body.length,
    });
    expect(footage?.durationS).toBeCloseTo(2, 1);
    expect(footage?.sha256).toMatch(/^[0-9a-f]{64}$/);
    expect(await noticesFor(id)).toEqual(["footage.ready"]);
  });

  it("rejects a renamed non-video file with the engine's guidance", async () => {
    const id = await probingFootage(readFileSync(join(clips, "notes.mp4")), "notes.mp4");
    await handler()({ footageId: id }, job());
    const footage = await findFootageById(db, id);
    expect(footage?.status).toBe("rejected");
    expect(footage?.rejectionReason).toMatch(/not a video we can read/);
    expect(await noticesFor(id)).toEqual(["footage.rejected"]);
  });

  it("skips footage that is no longer being probed, so retries are harmless", async () => {
    const body = readFileSync(join(clips, "clip.mp4"));
    const id = await probingFootage(body, "again.mp4");
    await handler()({ footageId: id }, job());
    const first = await findFootageById(db, id);
    await handler()({ footageId: id }, job());
    expect(await findFootageById(db, id)).toEqual(first);
    expect(await noticesFor(id)).toEqual(["footage.ready"]);
    await handler()({ footageId: newId() }, job());
  });

  it("retries while the engine is unreachable, then gives up with an explanation", async () => {
    const id = await probingFootage(readFileSync(join(clips, "clip.mp4")), "lost.mp4");
    const unreachable = footageProbeHandler({
      db,
      storage,
      engine: createEngineClient({ url: "http://127.0.0.1:9", token: TOKEN }),
      log: createLogger("silent"),
    });
    await expect(unreachable({ footageId: id }, job(0))).rejects.toThrow(/unreachable/);
    expect((await findFootageById(db, id))?.status).toBe("probing");
    await unreachable({ footageId: id }, job(6));
    expect(await findFootageById(db, id)).toMatchObject({
      status: "rejected",
      rejectionReason: expect.stringMatching(/several attempts/),
    });
    expect(await noticesFor(id)).toEqual(["footage.rejected"]);
  });

  it("refuses a worker without the service token", async () => {
    const id = await probingFootage(readFileSync(join(clips, "clip.mp4")), "token.mp4");
    const wrong = footageProbeHandler({
      db,
      storage,
      engine: createEngineClient({ url: engineUrl, token: "x".repeat(40) }),
      log: createLogger("silent"),
    });
    await expect(wrong({ footageId: id }, job(0))).rejects.toThrow(/401/);
  });
});
