import {
  claimPendingDeletions,
  type Db,
  markDeletionCompleted,
  recordDeletionFailure,
} from "@orrery/db";
import type { Storage } from "@orrery/storage";
import type { Logger } from "../logger.ts";

/** Objects removed per run. A run that fills its batch is followed by another at once. */
export const DELETION_BATCH = 100;

/**
 * Removes objects queued in `object_deletion`. Rows are claimed with SKIP LOCKED inside a
 * transaction, so two workers never delete the same object, and a crash mid-batch releases the
 * claim. Each object's own unfinished multipart uploads are aborted too. Failures stay pending
 * with their error and attempt count, and the next run retries them (requirement 6.5).
 */
export function objectsDeleteHandler(deps: { db: Db; storage: Storage; log: Logger }) {
  return async () => {
    let total = 0;
    for (;;) {
      const processed = await deps.db.transaction(async (tx) => {
        const batch = await claimPendingDeletions(tx, DELETION_BATCH);
        for (const row of batch) {
          try {
            await deps.storage.deleteObject(row.objectKey);
            await markDeletionCompleted(tx, row.id);
          } catch (error) {
            const message = error instanceof Error ? error.message : String(error);
            await recordDeletionFailure(tx, row.id, message);
            deps.log.warn(
              { deletion: row.id, attempts: row.attempts + 1 },
              "object deletion failed",
            );
          }
        }
        return batch.length;
      });
      total += processed;
      if (processed < DELETION_BATCH) break;
    }
    if (total > 0) deps.log.info({ objects: total }, "objects deleted");
  };
}
