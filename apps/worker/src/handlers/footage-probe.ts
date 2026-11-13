import { type Db, findFootageById, markFootageReady, markFootageRejected } from "@orrery/db";
import { footageProbe, type JobContext, type PayloadOf } from "@orrery/jobs";
import { MAX_FOOTAGE_BYTES, MAX_FOOTAGE_DURATION_S, type Storage } from "@orrery/storage";
import type { EngineClient } from "../engine.ts";
import type { Logger } from "../logger.ts";

/** The engine downloads the object with this URL; it only has to start within this time. */
const SOURCE_URL_SECONDS = 15 * 60;

/**
 * Asks the engine what an uploaded file really is, then marks the footage ready with its
 * properties or rejected with the engine's explanation. Footage that has left `probing` (deleted,
 * or already probed by an earlier attempt) is skipped, so retries are harmless.
 */
export function footageProbeHandler(deps: {
  db: Db;
  storage: Storage;
  engine: EngineClient;
  log: Logger;
}) {
  return async (payload: PayloadOf<typeof footageProbe>, job: JobContext) => {
    const footage = await findFootageById(deps.db, payload.footageId);
    if (footage?.status !== "probing") {
      deps.log.info({ job: job.id, footage: payload.footageId }, "probe skipped: not probing");
      return;
    }
    const sourceUrl = await deps.storage.presignGet(footage.objectKey, SOURCE_URL_SECONDS, {
      audience: "service",
    });
    let result: Awaited<ReturnType<EngineClient["probe"]>>;
    try {
      result = await deps.engine.probe(
        { sourceUrl, maxBytes: MAX_FOOTAGE_BYTES, maxDurationS: MAX_FOOTAGE_DURATION_S },
        job.signal,
      );
    } catch (error) {
      if (job.retryCount < footageProbe.retryLimit) throw error;
      await markFootageRejected(
        deps.db,
        footage.id,
        "We could not inspect this file after several attempts. Remove it and upload it again. If it fails again, the file may be damaged.",
      );
      deps.log.error({ err: error, job: job.id, footage: footage.id }, "probe gave up");
      return;
    }

    if (result.outcome === "rejected") {
      await markFootageRejected(deps.db, footage.id, result.reason);
      deps.log.info({ job: job.id, footage: footage.id, code: result.code }, "footage rejected");
      return;
    }
    if (result.byteSize !== footage.byteSize) {
      await markFootageRejected(
        deps.db,
        footage.id,
        "The stored file is not the size that was uploaded. Remove it and upload it again.",
      );
      return;
    }
    const { outcome: _outcome, ...probe } = result;
    await markFootageReady(deps.db, footage.id, probe);
    deps.log.info(
      { job: job.id, footage: footage.id, codec: probe.codec, durationS: probe.durationS },
      "footage ready",
    );
  };
}
