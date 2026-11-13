import { allQueues, objectsDelete } from "@orrery/jobs";

/** The worker counts as silent when its every-minute sweep has not finished for this long. */
const WORKER_STALE_MS = 3 * 60 * 1000;

import { z } from "zod";
import { DomainError } from "../domain-errors.ts";
import { requireAdmin } from "../policy.ts";
import { defineOperation } from "./define.ts";

// The operator page (requirement 7.4). Every operation requires the admin role; for anyone else
// the page does not exist (NotFound), like any other resource they cannot see.

const queueName = z.enum(
  allQueues.map((q) => q.name) as [string, ...string[]],
  "That queue does not exist.",
);

export const adminOverview = defineOperation({
  name: "admin.overview",
  input: z.object({}),
  run: async ({ actor, services }) => {
    requireAdmin(actor);
    const [queues, running, failed, storageOk, lastSweep] = await Promise.all([
      services.jobAdmin.summarize(),
      services.jobAdmin.recent(["active"], 50),
      services.jobAdmin.recent(["failed"], 50),
      services.storage.reachable(),
      services.jobAdmin.lastCompletion(objectsDelete.name),
    ]);
    // objects.delete runs every minute, so its last completion is the worker's heartbeat.
    const workerOk = lastSweep !== null && Date.now() - lastSweep.getTime() < WORKER_STALE_MS;
    return {
      status: {
        database: "ok" as const,
        storage: storageOk ? ("ok" as const) : ("unreachable" as const),
        worker: workerOk ? ("ok" as const) : ("silent" as const),
        workerLastSeen: lastSweep?.toISOString() ?? null,
      },
      queues,
      running,
      failed,
    };
  },
});

export const adminJobRetry = defineOperation({
  name: "admin.job.retry",
  input: z.object({ queue: queueName, jobId: z.uuid() }),
  run: async ({ actor, input, services }) => {
    requireAdmin(actor);
    if (!(await services.jobAdmin.retry(input.queue, input.jobId))) {
      throw new DomainError(
        "Conflict",
        "That job is not failed any more, so it cannot be retried.",
      );
    }
    return { retried: true as const };
  },
});

export const adminJobCancel = defineOperation({
  name: "admin.job.cancel",
  input: z.object({ queue: queueName, jobId: z.uuid() }),
  run: async ({ actor, input, services }) => {
    requireAdmin(actor);
    if (!(await services.jobAdmin.cancel(input.queue, input.jobId))) {
      throw new DomainError(
        "Conflict",
        "That job has already finished, so it cannot be cancelled.",
      );
    }
    return { cancelled: true as const };
  },
});
