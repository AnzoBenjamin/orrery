import { randomUUID } from "node:crypto";
import { enqueue } from "@orrery/jobs";
import { getRequestIP } from "@tanstack/react-start/server";
import type { z } from "zod";
import { database, databaseReady } from "./db.ts";
import type { Result } from "./domain-errors.ts";
import { serverEnv } from "./env.ts";
import { createJobAdmin } from "./job-admin.ts";
import { jobProducer } from "./jobs.ts";
import { invoke, type Operation, type Services } from "./operations/define.ts";
import { createLimits, type Limit } from "./rate-limits.ts";
import { requestActor } from "./request-actor.ts";
import { storage } from "./storage.ts";

const services: Services = {
  get storage() {
    return storage();
  },
  get quotaBytes() {
    return serverEnv().STORAGE_QUOTA_BYTES;
  },
  enqueue: async (queue, payload) => {
    await enqueue(await jobProducer(), queue, payload);
  },
  jobAdmin: createJobAdmin(jobProducer),
  limit: (name, key) => {
    limits ??= createLimits(database().pool);
    return limits(name, key);
  },
};

let limits: Limit | undefined;

/**
 * The body of every server function: resolve the actor, then invoke the operation. Unexpected
 * errors are logged with a reference the user can quote (GlitchTip reporting lands with 8.1).
 */
export async function call<TSchema extends z.ZodObject, TOutput>(
  op: Operation<TSchema, TOutput>,
  input: unknown,
): Promise<Result<TOutput>> {
  await databaseReady();
  const actor = await requestActor();
  // kamal-proxy (and the dev server) put the client's address first in X-Forwarded-For.
  const ip = getRequestIP({ xForwardedFor: true }) ?? null;
  return invoke({ db: database().db, services }, op, actor, input, {
    request: { ip },
    report: (error) => {
      const reference = randomUUID().slice(0, 8);
      process.stderr.write(
        `${JSON.stringify({ level: "error", reference, operation: op.name, error: String(error), stack: error instanceof Error ? error.stack : undefined })}\n`,
      );
      return reference;
    },
  });
}
