import { and, desc, eq, lt, sql } from "drizzle-orm";
import type { Executor } from "../client.ts";
import { footage, specimen } from "../schema/index.ts";
import { enqueueObjectDeletions } from "./object-deletions.ts";
import { clampLimit, type Page, type PageRequest, toPage } from "./page.ts";

export type Specimen = typeof specimen.$inferSelect;

export async function createSpecimen(
  ex: Executor,
  input: { ownerId: string; title: string; description?: string | undefined },
): Promise<Specimen> {
  const [row] = await ex
    .insert(specimen)
    .values({ ownerId: input.ownerId, title: input.title, description: input.description ?? "" })
    .returning();
  if (!row) throw new Error("specimen insert returned no row");
  return row;
}

/** Loads a specimen by id regardless of owner. Only the policy module should call this. */
export async function findSpecimenById(ex: Executor, id: string): Promise<Specimen | undefined> {
  const [row] = await ex.select().from(specimen).where(eq(specimen.id, id));
  return row;
}

export async function listSpecimensForOwner(
  ex: Executor,
  ownerId: string,
  page: PageRequest,
): Promise<Page<Specimen>> {
  const limit = clampLimit(page.limit);
  const rows = await ex
    .select()
    .from(specimen)
    .where(
      and(eq(specimen.ownerId, ownerId), page.before ? lt(specimen.id, page.before) : undefined),
    )
    .orderBy(desc(specimen.id))
    .limit(limit + 1);
  return toPage(rows, limit);
}

/** Updates title and description. Returns undefined when the specimen does not exist. */
export async function updateSpecimen(
  ex: Executor,
  id: string,
  changes: { title?: string | undefined; description?: string | undefined },
): Promise<Specimen | undefined> {
  const set: Partial<typeof specimen.$inferInsert> = {};
  if (changes.title !== undefined) set.title = changes.title;
  if (changes.description !== undefined) set.description = changes.description;
  if (Object.keys(set).length === 0) return findSpecimenById(ex, id);
  const [row] = await ex.update(specimen).set(set).where(eq(specimen.id, id)).returning();
  return row;
}

/**
 * Deletes a specimen with its footage and queues every stored object for removal, atomically.
 * Returns false when the specimen does not exist.
 */
export async function deleteSpecimen(ex: Executor, id: string): Promise<boolean> {
  return ex.transaction(async (tx) => {
    const [target] = await tx
      .select({ coverObjectKey: specimen.coverObjectKey })
      .from(specimen)
      .where(eq(specimen.id, id))
      .for("update");
    if (!target) return false;
    const footageKeys = await tx
      .select({ objectKey: footage.objectKey })
      .from(footage)
      .where(eq(footage.specimenId, id));
    const keys = footageKeys.map((f) => f.objectKey);
    if (target.coverObjectKey) keys.push(target.coverObjectKey);
    await enqueueObjectDeletions(tx, keys);
    await tx.delete(specimen).where(eq(specimen.id, id));
    return true;
  });
}

/**
 * Deletes every specimen an owner has, with their footage, and queues all of their stored objects
 * for removal, atomically. Used when an account is deleted: the user row's cascade would remove
 * the rows but leave their objects in storage. Returns the number of specimens deleted.
 */
export async function deleteSpecimensForOwner(ex: Executor, ownerId: string): Promise<number> {
  return ex.transaction(async (tx) => {
    const targets = await tx
      .select({ id: specimen.id, coverObjectKey: specimen.coverObjectKey })
      .from(specimen)
      .where(eq(specimen.ownerId, ownerId))
      .for("update");
    if (targets.length === 0) return 0;
    const footageKeys = await tx
      .select({ objectKey: footage.objectKey })
      .from(footage)
      .innerJoin(specimen, eq(footage.specimenId, specimen.id))
      .where(eq(specimen.ownerId, ownerId));
    const keys = footageKeys.map((f) => f.objectKey);
    for (const t of targets) if (t.coverObjectKey) keys.push(t.coverObjectKey);
    await enqueueObjectDeletions(tx, keys);
    await tx.delete(specimen).where(eq(specimen.ownerId, ownerId));
    return targets.length;
  });
}

export async function countSpecimensForOwner(ex: Executor, ownerId: string): Promise<number> {
  const [row] = await ex
    .select({ n: sql<number>`count(*)::int` })
    .from(specimen)
    .where(eq(specimen.ownerId, ownerId));
  return row?.n ?? 0;
}
