import { and, asc, eq, isNull, sql } from "drizzle-orm";
import type { Executor } from "../client.ts";
import { objectDeletion } from "../schema/index.ts";

export type ObjectDeletion = typeof objectDeletion.$inferSelect;

/** Records objects to remove from storage. The `objects.delete` job processes them. */
export async function enqueueObjectDeletions(ex: Executor, objectKeys: readonly string[]) {
  if (objectKeys.length === 0) return [];
  return ex
    .insert(objectDeletion)
    .values(objectKeys.map((objectKey) => ({ objectKey })))
    .returning();
}

/**
 * Locks up to `limit` pending deletions, oldest first. Rows locked by another worker are skipped,
 * so concurrent jobs never process the same object. Call inside a transaction.
 */
export async function claimPendingDeletions(ex: Executor, limit: number) {
  return ex
    .select()
    .from(objectDeletion)
    .where(isNull(objectDeletion.completedAt))
    .orderBy(asc(objectDeletion.createdAt))
    .limit(limit)
    .for("update", { skipLocked: true });
}

export async function markDeletionCompleted(ex: Executor, id: string) {
  const [row] = await ex
    .update(objectDeletion)
    .set({ completedAt: sql`now()`, lastError: null })
    .where(and(eq(objectDeletion.id, id), isNull(objectDeletion.completedAt)))
    .returning();
  return row;
}

export async function recordDeletionFailure(ex: Executor, id: string, error: string) {
  const [row] = await ex
    .update(objectDeletion)
    .set({ attempts: sql`${objectDeletion.attempts} + 1`, lastError: error.slice(0, 2000) })
    .where(eq(objectDeletion.id, id))
    .returning();
  return row;
}

export async function countPendingDeletions(ex: Executor): Promise<number> {
  const [row] = await ex
    .select({ n: sql<number>`count(*)::int` })
    .from(objectDeletion)
    .where(isNull(objectDeletion.completedAt));
  return row?.n ?? 0;
}
