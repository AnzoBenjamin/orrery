import { afterAll, beforeAll, inject } from "vitest";
import { user } from "../src/schema/index.ts";
import { createTestDatabase, type TestDatabase } from "../src/testing/index.ts";

/** One isolated, migrated database per test file. */
export function useTestDatabase(): () => TestDatabase {
  let database: TestDatabase | undefined;
  beforeAll(async () => {
    database = await createTestDatabase(inject("pgAdminUrl"));
  });
  afterAll(async () => {
    await database?.close();
  });
  return () => {
    if (!database) throw new Error("test database is not ready (used outside a test?)");
    return database;
  };
}

let userCounter = 0;

/**
 * Inserts a user row directly. This is the database package's own test suite, which tests the
 * tables themselves; product-level and end-to-end tests create users through sign-up instead.
 */
export async function insertUser(database: TestDatabase, name = "Test User") {
  userCounter += 1;
  const [row] = await database.db
    .insert(user)
    .values({ name, email: `user-${userCounter}-${Date.now()}@orrery.test` })
    .returning();
  if (!row) throw new Error("user insert returned no row");
  return row;
}
