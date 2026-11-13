import { type Db, deleteFootage, listFootageInStatusSince, markFootageProbing } from "@orrery/db";
import { footageProbe } from "@orrery/jobs";
import { type Storage, UPLOAD_TTL_SECONDS } from "@orrery/storage";
import type { Logger } from "../logger.ts";

/** Footage left in `probing` this long without a verdict has lost its job and is queued again. */
const PROBE_STALL_SECONDS = 30 * 60;
const BATCH = 200;

/**
 * Hourly cleanup of uploads (requirement 6.6):
 * - footage still `uploading` after 24 hours is finished if its object was fully assembled (the
 *   browser closed before reporting), and otherwise deleted with its partial upload;
 * - multipart uploads older than 24 hours that no footage owns are aborted in the store;
 * - footage stuck in `probing` (its job was never published) is queued for probing again.
 */
export function uploadsReapHandler(deps: {
  db: Db;
  storage: Storage;
  enqueue: (footageId: string) => Promise<void>;
  log: Logger;
  now?: () => Date;
}) {
  return async () => {
    const now = deps.now?.() ?? new Date();
    const expired = new Date(now.getTime() - UPLOAD_TTL_SECONDS * 1000);
    const finished = new Set<string>();
    let removed = 0;

    for (const f of await listFootageInStatusSince(deps.db, "uploading", expired, BATCH)) {
      const size = await deps.storage.objectSize(f.objectKey);
      if (size === f.byteSize) {
        if (await markFootageProbing(deps.db, f.id)) {
          await deps.enqueue(f.id);
          finished.add(f.id);
        }
      } else {
        // Queues the object for deletion; that also aborts any upload still open on its key.
        await deleteFootage(deps.db, { id: f.id, specimenId: f.specimenId });
        removed += 1;
      }
    }

    let aborted = 0;
    for (const upload of await deps.storage.listMultipartUploads()) {
      if (upload.initiatedAt < expired) {
        await deps.storage.abortMultipartUpload(upload.key, upload.uploadId);
        aborted += 1;
      }
    }

    const stalled = new Date(now.getTime() - PROBE_STALL_SECONDS * 1000);
    let requeued = 0;
    for (const f of await listFootageInStatusSince(deps.db, "probing", stalled, BATCH)) {
      if (finished.has(f.id)) continue;
      await deps.enqueue(f.id);
      requeued += 1;
    }

    if (finished.size + removed + aborted + requeued > 0) {
      deps.log.info(
        { finished: finished.size, removed, aborted, requeued, queue: footageProbe.name },
        "uploads reaped",
      );
    }
  };
}
