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
 * A user row for the operation layer's tests. Operations take an actor resolved from a session,
 * so these tests start from the user row; the end-to-end suite creates users through sign-up.
 */
export async function userActor(database: TestDatabase): Promise<Extract<Actor, { kind: "user" }>> {
  n += 1;
  const [row] = await database.db
    .insert(schema.user)
    .values({ name: `User ${n}`, email: `ops-${n}-${Date.now()}@orrery.test`, emailVerified: true })
    .returning();
  if (!row) throw new Error("no user row");
  return { kind: "user", userId: row.id, emailVerified: true, isAdmin: false };
}
