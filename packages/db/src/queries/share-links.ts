import { and, desc, eq, gt, isNull, or, sql } from "drizzle-orm";
import type { Executor } from "../client.ts";
import { shareLink } from "../schema/index.ts";

export type ShareLink = typeof shareLink.$inferSelect;

export async function createShareLink(
  ex: Executor,
  input: { specimenId: string; tokenHash: string; createdBy: string; expiresAt?: Date | undefined },
): Promise<ShareLink> {
  const [row] = await ex
    .insert(shareLink)
    .values({ ...input, expiresAt: input.expiresAt ?? null })
    .returning();
  if (!row) throw new Error("share link insert returned no row");
  return row;
}

/** Loads a link by id regardless of owner. Only operations that then check the specimen use it. */
export async function findShareLinkById(ex: Executor, id: string): Promise<ShareLink | undefined> {
  const [row] = await ex.select().from(shareLink).where(eq(shareLink.id, id));
  return row;
}

/** Every link of a specimen, including revoked and expired ones, newest first. */
export async function listShareLinks(ex: Executor, specimenId: string): Promise<ShareLink[]> {
  return ex
    .select()
    .from(shareLink)
    .where(eq(shareLink.specimenId, specimenId))
    .orderBy(desc(shareLink.id));
}

export async function revokeShareLink(
  ex: Executor,
  input: { id: string; specimenId: string },
): Promise<ShareLink | undefined> {
  const [row] = await ex
    .update(shareLink)
    .set({ revokedAt: sql`now()` })
    .where(
      and(
        eq(shareLink.id, input.id),
        eq(shareLink.specimenId, input.specimenId),
        isNull(shareLink.revokedAt),
      ),
    )
    .returning();
  return row;
}

/**
 * Resolves a token hash to an active link (not revoked, not expired) and records the use.
 * Returns undefined for unknown, revoked, and expired links alike.
 */
export async function resolveShareLink(
  ex: Executor,
  tokenHash: string,
  now: Date,
): Promise<ShareLink | undefined> {
  const [row] = await ex
    .update(shareLink)
    .set({ lastUsedAt: now })
    .where(
      and(
        eq(shareLink.tokenHash, tokenHash),
        isNull(shareLink.revokedAt),
        or(isNull(shareLink.expiresAt), gt(shareLink.expiresAt, now)),
      ),
    )
    .returning();
  return row;
}
