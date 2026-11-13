import {
  createNotification,
  type Db,
  type Footage,
  findFootageById,
  findSpecimenById,
  markFootageReady,
  markFootageRejected,
  type ProbeResult,
} from "@orrery/db";
import { footageProbe, type JobContext, type PayloadOf } from "@orrery/jobs";
import { MAX_FOOTAGE_BYTES, MAX_FOOTAGE_DURATION_S, type Storage } from "@orrery/storage";
import type { EngineClient } from "../engine.ts";
import type { Logger } from "../logger.ts";

/** The engine downloads the object with this URL; it only has to start within this time. */
const SOURCE_URL_SECONDS = 15 * 60;

const GAVE_UP =
  "We could not inspect this file after several attempts. Remove it and upload it again. If it fails again, the file may be damaged.";

/**
 * Asks the engine what an uploaded file really is, then marks the footage ready with its
 * properties or rejected with the engine's explanation, and tells the owner in the same
 * transaction. Footage that has left `probing` (deleted, or already probed by an earlier
 * attempt) is skipped, so retries are harmless. When the retries run out the footage is marked
 * rejected with a reason the user can act on (requirement 7.3).
 */
export function footageProbeHandler(deps: {
  db: Db;
  storage: Storage;
  engine: EngineClient;
  log: Logger;
}) {
  async function settle(footage: Footage, verdict: { ready: ProbeResult } | { reason: string }) {
    await deps.db.transaction(async (tx) => {
      const changed =
        "ready" in verdict
          ? await markFootageReady(tx, footage.id, verdict.ready)
          : await markFootageRejected(tx, footage.id, verdict.reason);
      const specimen = changed ? await findSpecimenById(tx, footage.specimenId) : undefined;
      if (!specimen) return;
      const about = {
        specimenId: specimen.id,
        specimenTitle: specimen.title,
        footageId: footage.id,
        filename: footage.originalFilename,
      };
      await createNotification(
        tx,
        "ready" in verdict
          ? { userId: specimen.ownerId, kind: "footage.ready", payload: about }
          : {
              userId: specimen.ownerId,
              kind: "footage.rejected",
              payload: { ...about, reason: verdict.reason },
            },
      );
    });
  }

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
      await settle(footage, { reason: GAVE_UP });
      deps.log.error({ err: error, job: job.id, footage: footage.id }, "probe gave up");
      return;
    }

    if (result.outcome === "rejected") {
      await settle(footage, { reason: result.reason });
      deps.log.info({ job: job.id, footage: footage.id, code: result.code }, "footage rejected");
      return;
    }
    if (result.byteSize !== footage.byteSize) {
      await settle(footage, {
        reason: "The stored file is not the size that was uploaded. Remove it and upload it again.",
      });
      return;
    }
    const { outcome: _outcome, ...probe } = result;
    await settle(footage, { ready: probe });
    deps.log.info(
      { job: job.id, footage: footage.id, codec: probe.codec, durationS: probe.durationS },
      "footage ready",
    );
  };
}
