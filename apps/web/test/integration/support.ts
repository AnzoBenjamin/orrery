import { randomBytes } from "node:crypto";
import { schema } from "@orrery/db";
import { createTestDatabase, type TestDatabase } from "@orrery/db/testing";
import { afterAll, beforeAll, inject } from "vitest";
import type { Actor } from "../../src/server/actor.ts";

export function withTestDatabase(): () => TestDatabase {
  let database: TestDatabase | undefined;
  beforeAll(async () => {
    database = await createTestDatabase(inject("pgAdminUrl"));
  });
  afterAll(async () => {
    await database?.close();
  });
  return () => {
    if (!database) throw new Error("test database is not ready");
    return database;
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
