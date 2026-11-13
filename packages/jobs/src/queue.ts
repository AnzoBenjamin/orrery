import { currentTraceparent, inSpan, reportError } from "@orrery/telemetry";
import type { PgBoss } from "pg-boss";
import { v5 as uuidv5 } from "uuid";
import type { z } from "zod";

/** Namespace for job ids derived from idempotency keys (a fixed, random UUID). */
const JOB_ID_NAMESPACE = "5d0b3c1e-8a77-4f5e-9a51-3b8f6a0e2c41";

/**
 * One job type: its payload schema, retry policy, timeout, and idempotency key (requirement 7.2).
 * `enqueue` and `work` are the only ways to publish and consume, so payloads are validated on
 * both sides of the queue.
 */
export interface QueueDefinition<TSchema extends z.ZodType> {
  readonly name: string;
  readonly schema: TSchema;
  readonly retryLimit: number;
  /** Seconds before the first retry. With `retryBackoff`, later retries double it. */
  readonly retryDelaySeconds: number;
  readonly retryBackoff: boolean;
  /** A job running longer than this is failed and retried. */
  readonly expireInSeconds: number;
  /**
   * A job with the same key is never created twice while the first one is retained (queued,
   * running, retrying, or within the completed-job retention window). The key becomes the job id
   * through UUIDv5. Returning undefined allows duplicates.
   */
  readonly idempotencyKey: (payload: z.output<TSchema>) => string | undefined;
}

export function defineQueue<TSchema extends z.ZodType>(
  definition: QueueDefinition<TSchema>,
): QueueDefinition<TSchema> {
  if (!/^[a-z]+(\.[a-z]+)+$/.test(definition.name)) {
    throw new Error(`queue name ${definition.name} must look like "area.action"`);
  }
  return definition;
}

export type AnyQueue = QueueDefinition<z.ZodType>;
export type PayloadOf<Q> = Q extends QueueDefinition<infer S> ? z.output<S> : never;

/** Creates or updates every queue's stored policy. Run by the worker at startup. */
export async function ensureQueues(boss: PgBoss, queues: readonly AnyQueue[]): Promise<void> {
  for (const q of queues) {
    const options = {
      retryLimit: q.retryLimit,
      retryDelay: q.retryDelaySeconds,
      retryBackoff: q.retryBackoff,
      expireInSeconds: q.expireInSeconds,
    };
    if (await boss.getQueue(q.name)) await boss.updateQueue(q.name, options);
    else await boss.createQueue(q.name, options);
  }
}

export class InvalidJobPayloadError extends Error {
  constructor(queue: string, issues: string) {
    super(`invalid payload for ${queue}: ${issues}`);
    this.name = "InvalidJobPayloadError";
  }
}

function parse<TSchema extends z.ZodType>(q: QueueDefinition<TSchema>, data: unknown) {
  const result = q.schema.safeParse(data);
  if (!result.success) {
    throw new InvalidJobPayloadError(
      q.name,
      result.error.issues.map((i) => `${i.path.join(".") || "(root)"}: ${i.message}`).join("; "),
    );
  }
  return result.data;
}

/** The job id used for an idempotency key on a queue. */
export function jobIdFor(queue: string, idempotencyKey: string): string {
  return uuidv5(`${queue}\u0000${idempotencyKey}`, JOB_ID_NAMESPACE);
}

/**
 * Validates and publishes a job. Returns the job id, or null when a job with the same
 * idempotency key already exists. The active trace travels with the job (requirement 11.1).
 */
export async function enqueue<TSchema extends z.ZodType>(
  boss: PgBoss,
  q: QueueDefinition<TSchema>,
  payload: z.input<TSchema>,
  options: { startAfter?: Date | undefined; traceparent?: string | undefined } = {},
): Promise<string | null> {
  const data = parse(q, payload);
  const key = q.idempotencyKey(data);
  return boss.send(
    q.name,
    { payload: data, traceparent: options.traceparent ?? currentTraceparent() ?? null },
    {
      ...(key === undefined ? {} : { id: jobIdFor(q.name, key) }),
      ...(options.startAfter === undefined ? {} : { startAfter: options.startAfter }),
    },
  );
}

/**
 * Runs a queue on a cron schedule (UTC). Every scheduled job carries the same validated payload.
 * Re-scheduling replaces the previous schedule, so the worker can call this at every start.
 */
export async function scheduleQueue<TSchema extends z.ZodType>(
  boss: PgBoss,
  q: QueueDefinition<TSchema>,
  cron: string,
  payload: z.input<TSchema>,
): Promise<void> {
  await boss.schedule(
    q.name,
    cron,
    { payload: parse(q, payload), traceparent: null },
    { tz: "UTC" },
  );
}

export interface JobContext {
  id: string;
  retryCount: number;
  /** W3C trace context of the request that enqueued the job, for span linking. */
  traceparent: string | null;
  signal: AbortSignal;
}

/**
 * Registers a handler. Payloads are re-validated on receipt, because a job may have been queued
 * by an older release. A thrown error fails the attempt and pg-boss retries per the definition.
 */
export async function work<TSchema extends z.ZodType>(
  boss: PgBoss,
  q: QueueDefinition<TSchema>,
  handler: (payload: z.output<TSchema>, context: JobContext) => Promise<void>,
  options: { concurrency?: number } = {},
): Promise<string> {
  return boss.work<{ payload: unknown; traceparent: string | null }>(
    q.name,
    { batchSize: 1, localConcurrency: options.concurrency ?? 1 },
    async (jobs) => {
      for (const job of jobs) {
        await inSpan(
          `job ${q.name}`,
          job.data.traceparent,
          { "job.queue": q.name, "job.id": job.id, "job.attempt": job.retryCount + 1 },
          async () => {
            try {
              const payload = parse(q, job.data.payload);
              await handler(payload, {
                id: job.id,
                retryCount: job.retryCount,
                traceparent: job.data.traceparent,
                signal: job.signal,
              });
            } catch (error) {
              // Only the last attempt's failure is an incident; earlier ones are retried.
              if (job.retryCount >= q.retryLimit) {
                reportError(error, { queue: q.name, job: job.id });
              }
              throw error;
            }
          },
        );
      }
    },
  );
}
