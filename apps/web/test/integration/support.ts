import { randomBytes } from "node:crypto";
import { schema } from "@orrery/db";
import { createTestDatabase, type TestDatabase } from "@orrery/db/testing";
import { allQueues, createProducer, enqueue, ensureQueues, migrateJobSchema } from "@orrery/jobs";
import { Storage } from "@orrery/storage";
import type { PgBoss } from "pg-boss";
import { afterAll, beforeAll, inject } from "vitest";
import type { Actor } from "../../src/server/actor.ts";
import { createJobAdmin } from "../../src/server/job-admin.ts";
import type { Deps } from "../../src/server/operations/define.ts";
import { createLimits } from "../../src/server/rate-limits.ts";

export interface TestEnv extends TestDatabase {
  /** What operations run against: this database, the test Garage, and pg-boss on this database. */
  deps: Deps;
  boss: PgBoss;
  storage: Storage;
}

/** Storage quota in tests: small, so the quota check can be reached with small files. */
export const TEST_QUOTA_BYTES = 50_000_000;

/** One migrated database per test file, with the real object store and job queue. */
export function withTestDatabase(): () => TestEnv {
  let env: TestEnv | undefined;
  beforeAll(async () => {
    const database = await createTestDatabase(inject("pgAdminUrl"));
    await migrateJobSchema(database.url);
    const boss = createProducer(database.url);
    await boss.start();
    await ensureQueues(boss, allQueues);
    const storage = new Storage(inject("garage"));
    env = {
      ...database,
      boss,
      storage,
      deps: {
        db: database.db,
        services: {
          storage,
          quotaBytes: TEST_QUOTA_BYTES,
          enqueue: async (queue, payload) => {
            await enqueue(boss, queue, payload);
          },
          limit: createLimits(database.pool),
          jobAdmin: createJobAdmin(async () => boss),
        },
      },
    };
  });
  afterAll(async () => {
    await env?.boss.stop({ graceful: false });
    env?.storage.destroy();
    await env?.close();
  });
  return () => {
    if (!env) throw new Error("test database is not ready");
    return env;
  };
}

let n = 0;

/**
 * A user row with one session for the operation layer's tests. Operations take an actor resolved
 * from a session, so these tests start from the rows; the end-to-end suite signs up instead.
 */
export async function userActor(database: TestDatabase): Promise<Extract<Actor, { kind: "user" }>> {
  n += 1;
  const [row] = await database.db
    .insert(schema.user)
    .values({ name: `User ${n}`, email: `ops-${n}-${Date.now()}@orrery.test`, emailVerified: true })
    .returning();
  if (!row) throw new Error("no user row");
  const [current] = await database.db
    .insert(schema.session)
    .values({
      userId: row.id,
      token: randomBytes(24).toString("hex"),
      expiresAt: new Date(Date.now() + 3_600_000),
      updatedAt: new Date(),
      userAgent: "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/140.0 Safari/537.36",
      ipAddress: "198.51.100.4",
    })
    .returning();
  if (!current) throw new Error("no session row");
  return {
    kind: "user",
    userId: row.id,
    sessionId: current.id,
    emailVerified: true,
    isAdmin: false,
  };
}
