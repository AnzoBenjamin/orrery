import type { PgBoss } from "pg-boss";
import { z } from "zod";
import { PG_BOSS_SCHEMA } from "./boss.ts";
import type { AnyQueue } from "./queue.ts";

/**
 * What the operator page shows about the queues (requirement 7.4). Counts and recent jobs are
 * read from pg-boss's job table through its own database adapter, because its API cannot list
 * jobs by state and its counts lag behind. Rows are validated, so a pg-boss upgrade that changes the table
 * fails here loudly instead of rendering wrong data.
 */

export interface QueueSummary {
  name: string;
  queued: number;
  active: number;
  failed: number;
  deferred: number;
}

export type JobState = "active" | "failed" | "retry" | "created";

const jobRow = z.object({
  id: z.uuid(),
  name: z.string(),
  state: z.enum(["created", "retry", "active", "completed", "cancelled", "failed"]),
  retry_count: z.number().int(),
  retry_limit: z.number().int(),
  created_on: z.date(),
  started_on: z.date().nullable(),
  completed_on: z.date().nullable(),
  output: z.unknown().nullable(),
});

export interface JobSummary {
  id: string;
  queue: string;
  state: z.output<typeof jobRow>["state"];
  attempts: number;
  retryLimit: number;
  createdAt: string;
  startedAt: string | null;
  finishedAt: string | null;
  /** The error a failed attempt recorded, without its stack. */
  error: string | null;
}

function errorOf(output: unknown): string | null {
  if (output && typeof output === "object" && "message" in output) {
    const message = (output as { message: unknown }).message;
    if (typeof message === "string") return message.slice(0, 500);
  }
  return null;
}

const countRow = z.object({
  name: z.string(),
  state: z.string(),
  deferred: z.boolean(),
  n: z.coerce.number(),
});

/**
 * Live counts per queue and state. pg-boss's own queue counts are refreshed by its monitor,
 * which only the worker runs, so they are counted here directly.
 */
export async function summarizeQueues(
  boss: PgBoss,
  queues: readonly AnyQueue[],
): Promise<QueueSummary[]> {
  const { rows } = await boss.getDb().executeSql(
    `select name, state::text as state, (start_after > now()) as deferred, count(*) as n
       from ${PG_BOSS_SCHEMA}.job
      where name = any($1::text[]) and state::text in ('created', 'retry', 'active', 'failed')
      group by 1, 2, 3`,
    [queues.map((q) => q.name)],
  );
  const counts = rows.map((r) => countRow.parse(r));
  return queues.map((q) => {
    const mine = counts.filter((c) => c.name === q.name);
    const sum = (pick: (c: z.output<typeof countRow>) => boolean) =>
      mine.filter(pick).reduce((total, c) => total + c.n, 0);
    return {
      name: q.name,
      queued: sum((c) => (c.state === "created" || c.state === "retry") && !c.deferred),
      deferred: sum((c) => (c.state === "created" || c.state === "retry") && c.deferred),
      active: sum((c) => c.state === "active"),
      failed: sum((c) => c.state === "failed"),
    };
  });
}

/** The most recent jobs in `states`, newest first, across the given queues. */
export async function recentJobs(
  boss: PgBoss,
  queues: readonly AnyQueue[],
  states: readonly JobState[],
  limit: number,
): Promise<JobSummary[]> {
  const { rows } = await boss.getDb().executeSql(
    `select id, name, state::text as state, retry_count, retry_limit, created_on, started_on,
              completed_on, output
         from ${PG_BOSS_SCHEMA}.job
        where name = any($1::text[]) and state::text = any($2::text[])
        order by coalesce(completed_on, started_on, created_on) desc
        limit $3`,
    [queues.map((q) => q.name), [...states], Math.min(Math.max(limit, 1), 200)],
  );
  return rows.map((raw) => {
    const r = jobRow.parse(raw);
    return {
      id: r.id,
      queue: r.name,
      state: r.state,
      attempts: r.retry_count + (r.state === "created" ? 0 : 1),
      retryLimit: r.retry_limit,
      createdAt: r.created_on.toISOString(),
      startedAt: r.started_on?.toISOString() ?? null,
      finishedAt: r.completed_on?.toISOString() ?? null,
      error: errorOf(r.output),
    };
  });
}

/** Re-queues a failed job. Returns false when the job is not in a retryable state. */
export async function retryJob(boss: PgBoss, queue: string, id: string): Promise<boolean> {
  const result = await boss.retry(queue, id);
  return result.affected > 0;
}

/** Cancels a queued, retrying, or running job. Returns false when it has already finished. */
export async function cancelJob(boss: PgBoss, queue: string, id: string): Promise<boolean> {
  const result = await boss.cancel(queue, id);
  return result.affected > 0;
}

/** When a job of `queue` last completed, or null if none is retained. */
export async function lastCompletion(boss: PgBoss, queue: string): Promise<Date | null> {
  const { rows } = await boss
    .getDb()
    .executeSql(
      `select max(completed_on) as at from ${PG_BOSS_SCHEMA}.job where name = $1 and state = 'completed'`,
      [queue],
    );
  const at = z.object({ at: z.date().nullable() }).parse(rows[0] ?? { at: null }).at;
  return at;
}
