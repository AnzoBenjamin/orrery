import { and, desc, eq, sql } from "drizzle-orm";
import type { Executor } from "../client.ts";
import { footage, specimen } from "../schema/index.ts";
import { enqueueObjectDeletions } from "./object-deletions.ts";

export type Footage = typeof footage.$inferSelect;
export type FootageRole = Footage["role"];

export async function createFootage(
  ex: Executor,
  input: {
    id: string;
    specimenId: string;
    role: FootageRole;
    objectKey: string;
    originalFilename: string;
    byteSize: number;
  },
): Promise<Footage> {
  const [row] = await ex.insert(footage).values(input).returning();
  if (!row) throw new Error("footage insert returned no row");
  return row;
}

export async function findFootage(
  ex: Executor,
  input: { id: string; specimenId: string },
): Promise<Footage | undefined> {
  const [row] = await ex
    .select()
    .from(footage)
    .where(and(eq(footage.id, input.id), eq(footage.specimenId, input.specimenId)));
  return row;
}

/** All footage of a specimen, newest first. A specimen holds tens of clips, not thousands. */
export async function listFootageForSpecimen(ex: Executor, specimenId: string): Promise<Footage[]> {
  return ex
    .select()
    .from(footage)
    .where(eq(footage.specimenId, specimenId))
    .orderBy(desc(footage.id));
}

/** uploading → probing. Returns undefined if the footage is not in `uploading`. */
export async function markFootageProbing(ex: Executor, id: string): Promise<Footage | undefined> {
  const [row] = await ex
    .update(footage)
    .set({ status: "probing" })
    .where(and(eq(footage.id, id), eq(footage.status, "uploading")))
    .returning();
  return row;
}

export interface ProbeResult {
  sha256: string;
  byteSize: number;
  durationS: number;
  width: number;
  height: number;
  fpsNominal: number;
  isVfr: boolean;
  codec: string;
  rotationQuarterTurns: 0 | 1 | 2 | 3;
}

/** probing → ready, recording the probe. Returns undefined if the footage is not in `probing`. */
export async function markFootageReady(
  ex: Executor,
  id: string,
  probe: ProbeResult,
): Promise<Footage | undefined> {
  const [row] = await ex
    .update(footage)
    .set({ ...probe, status: "ready", rejectionReason: null })
    .where(and(eq(footage.id, id), eq(footage.status, "probing")))
    .returning();
  return row;
}

/** uploading or probing → rejected with a user-readable reason. */
export async function markFootageRejected(
  ex: Executor,
  id: string,
  reason: string,
): Promise<Footage | undefined> {
  const [row] = await ex
    .update(footage)
    .set({ status: "rejected", rejectionReason: reason })
    .where(and(eq(footage.id, id), sql`${footage.status} in ('uploading', 'probing')`))
    .returning();
  return row;
}

/** Deletes the footage row and queues its object for removal, atomically. */
export async function deleteFootage(
  ex: Executor,
  input: { id: string; specimenId: string },
): Promise<boolean> {
  return ex.transaction(async (tx) => {
    const [row] = await tx
      .delete(footage)
      .where(and(eq(footage.id, input.id), eq(footage.specimenId, input.specimenId)))
      .returning({ objectKey: footage.objectKey });
    if (!row) return false;
    await enqueueObjectDeletions(tx, [row.objectKey]);
    return true;
  });
}

/** Bytes of footage the user stores across all specimens, including uploads in progress. */
export async function storageBytesForOwner(ex: Executor, ownerId: string): Promise<number> {
  const [row] = await ex
    .select({ bytes: sql<string>`coalesce(sum(${footage.byteSize}), 0)` })
    .from(footage)
    .innerJoin(specimen, eq(specimen.id, footage.specimenId))
    .where(eq(specimen.ownerId, ownerId));
  return Number(row?.bytes ?? 0);
}
