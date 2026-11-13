import { randomUUID } from "node:crypto";
import type { z } from "zod";
import { database, databaseReady } from "./db.ts";
import type { Result } from "./domain-errors.ts";
import { invoke, type Operation } from "./operations/define.ts";
import { requestActor } from "./request-actor.ts";

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
  return invoke(database().db, op, actor, input, {
    report: (error) => {
      const reference = randomUUID().slice(0, 8);
      process.stderr.write(
        `${JSON.stringify({ level: "error", reference, operation: op.name, error: String(error), stack: error instanceof Error ? error.stack : undefined })}\n`,
      );
      return reference;
    },
  });
}
