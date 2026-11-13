import { randomUUID } from "node:crypto";
import { enqueue } from "@orrery/jobs";
import type { z } from "zod";
import { database, databaseReady } from "./db.ts";
import type { Result } from "./domain-errors.ts";
import { serverEnv } from "./env.ts";
import { jobProducer } from "./jobs.ts";
import { invoke, type Operation, type Services } from "./operations/define.ts";
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
};

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
  return invoke({ db: database().db, services }, op, actor, input, {
    report: (error) => {
      const reference = randomUUID().slice(0, 8);
      process.stderr.write(
        `${JSON.stringify({ level: "error", reference, operation: op.name, error: String(error), stack: error instanceof Error ? error.stack : undefined })}\n`,
      );
      return reference;
    },
  });
}
