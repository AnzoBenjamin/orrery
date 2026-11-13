import { database } from "./db.ts";
import { createLimits, type Limit } from "./rate-limits.ts";

let limits: Limit | undefined;

/** The process's rate limits, shared by server functions and the Better Auth hook. */
export const appLimits: Limit = (name, key) => {
  limits ??= createLimits(database().pool);
  return limits(name, key);
};
