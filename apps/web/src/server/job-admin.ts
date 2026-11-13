import {
  allQueues,
  cancelJob,
  lastCompletion,
  recentJobs,
  retryJob,
  summarizeQueues,
} from "@orrery/jobs";
import type { PgBoss } from "pg-boss";
import type { JobAdmin } from "./operations/define.ts";

/** Operator access to every queue the worker serves, through one pg-boss client. */
export function createJobAdmin(boss: () => Promise<PgBoss>): JobAdmin {
  return {
    summarize: async () => summarizeQueues(await boss(), allQueues),
    recent: async (states, limit) => recentJobs(await boss(), allQueues, states, limit),
    retry: async (queue, id) => retryJob(await boss(), queue, id),
    cancel: async (queue, id) => cancelJob(await boss(), queue, id),
    lastCompletion: async (queue) => lastCompletion(await boss(), queue),
  };
}
