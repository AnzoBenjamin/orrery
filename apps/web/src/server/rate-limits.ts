import type { DbHandle } from "@orrery/db";
import { RateLimiterPostgres, RateLimiterRes } from "rate-limiter-flexible";
import { DomainError } from "./domain-errors.ts";

/**
 * Application rate limits (requirement 12.3), counted in Postgres so every web process shares
 * them. The `request_limit` table comes from a migration; the library never creates it.
 */
const ACCOUNT_LEAD = "Too many attempts for this account.";

/** Each policy's `lead` opens the message shown when its limit is used up. */
export const limitPolicies = {
  /** Opening a share link or playing its footage, per client IP. */
  "share-access": { points: 120, durationSeconds: 60, lead: "Too many requests." },
  /** Signing upload steps, per user. A 1 GB file needs about 130 signatures. */
  "upload-sign": { points: 1200, durationSeconds: 60, lead: "Too many requests." },
  /**
   * Per-account auth limits (requirement 4.4), keyed by a digest of the email address, so
   * guessing one account's password from many addresses is stopped as well as from one. Better
   * Auth's own limits cover each IP. Counted whether or not the account exists, so a refusal
   * reveals nothing about which addresses have accounts.
   */
  "sign-in-account": { points: 10, durationSeconds: 900, lead: ACCOUNT_LEAD },
  "sign-up-account": { points: 5, durationSeconds: 3600, lead: ACCOUNT_LEAD },
  "password-reset-account": { points: 3, durationSeconds: 3600, lead: ACCOUNT_LEAD },
  "verification-email-account": { points: 3, durationSeconds: 3600, lead: ACCOUNT_LEAD },
} as const;

export type LimitName = keyof typeof limitPolicies;

export type Limit = (name: LimitName, key: string) => Promise<void>;

/** "45 seconds" under two minutes, whole minutes (rounded up) from there. */
export function waitText(ms: number): string {
  const seconds = Math.max(1, Math.ceil(ms / 1000));
  if (seconds < 120) return `${seconds} second${seconds === 1 ? "" : "s"}`;
  return `${Math.ceil(seconds / 60)} minutes`;
}

export function createLimits(pool: DbHandle["pool"]): Limit {
  const limiters = new Map(
    Object.entries(limitPolicies).map(([name, policy]) => [
      name,
      {
        lead: policy.lead,
        limiter: new RateLimiterPostgres({
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
      },
    ]),
  );
  return async (name, key) => {
    const entry = limiters.get(name);
    if (!entry) throw new Error(`unknown rate limit ${name}`);
    try {
      await entry.limiter.consume(key);
    } catch (error) {
      if (error instanceof RateLimiterRes) {
        const wait = waitText(error.msBeforeNext);
        throw new DomainError("RateLimited", `${entry.lead} Wait ${wait}, then try again.`);
      }
      throw error;
    }
  };
}
