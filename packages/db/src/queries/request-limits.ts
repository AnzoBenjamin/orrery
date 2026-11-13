import { lt } from "drizzle-orm";
import type { Executor } from "../client.ts";
import { requestLimit } from "../schema/index.ts";

/** Deletes rate-limit counters whose window ended before `nowMs`. Returns how many. */
export async function deleteExpiredRequestLimits(ex: Executor, nowMs: number): Promise<number> {
  const rows = await ex
    .delete(requestLimit)
    .where(lt(requestLimit.expire, nowMs))
    .returning({ key: requestLimit.key });
  return rows.length;
}
