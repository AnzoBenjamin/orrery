import { and, asc, eq, isNull, lt, sql } from "drizzle-orm";
import type { Executor } from "../client.ts";
import { uploadSession } from "../schema/index.ts";

export type UploadSession = typeof uploadSession.$inferSelect;

export async function createUploadSession(
  ex: Executor,
  input: { footageId: string; s3UploadId: string; partSize: number; expiresAt: Date },
): Promise<UploadSession> {
  const [row] = await ex.insert(uploadSession).values(input).returning();
  if (!row) throw new Error("upload session insert returned no row");
  return row;
}

/** The upload session of a footage item, open or completed. */
export async function findUploadSession(
  ex: Executor,
  footageId: string,
): Promise<UploadSession | undefined> {
  const [row] = await ex.select().from(uploadSession).where(eq(uploadSession.footageId, footageId));
  return row;
}

/** The session of a footage item, if its upload is still open and not expired. */
export async function findOpenUploadSession(
  ex: Executor,
  footageId: string,
  now: Date,
): Promise<UploadSession | undefined> {
  const [row] = await ex
    .select()
    .from(uploadSession)
    .where(
      and(
        eq(uploadSession.footageId, footageId),
        isNull(uploadSession.completedAt),
        sql`${uploadSession.expiresAt} > ${now.toISOString()}`,
      ),
    );
  return row;
}

export async function completeUploadSession(
  ex: Executor,
  id: string,
): Promise<UploadSession | undefined> {
  const [row] = await ex
    .update(uploadSession)
    .set({ completedAt: sql`now()` })
    .where(and(eq(uploadSession.id, id), isNull(uploadSession.completedAt)))
    .returning();
  return row;
}

/** Open sessions past their expiry, oldest first, for the `uploads.reap` job. */
export async function listExpiredUploadSessions(
  ex: Executor,
  now: Date,
  limit: number,
): Promise<UploadSession[]> {
  return ex
    .select()
    .from(uploadSession)
    .where(and(isNull(uploadSession.completedAt), lt(uploadSession.expiresAt, now)))
    .orderBy(asc(uploadSession.expiresAt))
    .limit(limit);
}

export async function deleteUploadSession(ex: Executor, id: string): Promise<boolean> {
  const rows = await ex
    .delete(uploadSession)
    .where(eq(uploadSession.id, id))
    .returning({ id: uploadSession.id });
  return rows.length > 0;
}
