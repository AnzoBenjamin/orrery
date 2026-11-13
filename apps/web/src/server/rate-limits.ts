import type { DbHandle } from "@orrery/db";
import { RateLimiterPostgres, RateLimiterRes } from "rate-limiter-flexible";
import { DomainError } from "./domain-errors.ts";

/**
 * Application rate limits (requirement 12.3), counted in Postgres so every web process shares
 * them. The `request_limit` table comes from a migration; the library never creates it.
 */
export const limitPolicies = {
  /** Opening a share link or playing its footage, per client IP. */
  "share-access": { points: 120, durationSeconds: 60 },
  /** Signing upload steps, per user. A 1 GB file needs about 130 signatures. */
  "upload-sign": { points: 1200, durationSeconds: 60 },
} as const;

export type LimitName = keyof typeof limitPolicies;

export type Limit = (name: LimitName, key: string) => Promise<void>;

export function createLimits(pool: DbHandle["pool"]): Limit {
  const limiters = new Map(
    Object.entries(limitPolicies).map(([name, policy]) => [
      name,
      new RateLimiterPostgres({
        storeClient: pool,
        storeType: "pool",
        tableName: "request_limit",
        tableCreated: true,
        // Expired rows are removed by the worker's limits.prune job.
        clearExpiredByTimeout: false,
        keyPrefix: name,
        points: policy.points,
        duration: policy.durationSeconds,
      }),
    ]),
  );
  return async (name, key) => {
    const limiter = limiters.get(name);
    if (!limiter) throw new Error(`unknown rate limit ${name}`);
    try {
      await limiter.consume(key);
    } catch (error) {
      if (error instanceof RateLimiterRes) {
        const seconds = Math.max(1, Math.ceil(error.msBeforeNext / 1000));
        throw new DomainError(
          "RateLimited",
          `Too many requests. Wait ${seconds} second${seconds === 1 ? "" : "s"}, then try again.`,
        );
      }
      throw error;
    }
  };
}
