import { readMigrationFiles } from "drizzle-orm/migrator";
import { describe, expect, inject, it } from "vitest";
import {
  assertMigrationsApplied,
  MigrationsPendingError,
  migrationsFolder,
  runMigrations,
} from "../src/migrate.ts";
import { createTestDatabase } from "../src/testing/index.ts";

const migrationCount = readMigrationFiles({ migrationsFolder }).length;

describe("migrations", () => {
  it("refuses to boot against a database with unapplied migrations, naming them", async () => {
    const database = await createTestDatabase(inject("pgAdminUrl"), { migrated: false });
    try {
      const error = await assertMigrationsApplied(database.db).then(
        () => undefined,
        (e: unknown) => e,
      );
      expect(error).toBeInstanceOf(MigrationsPendingError);
      expect((error as MigrationsPendingError).pending).toContain("0000_core");
      expect((error as Error).message).toContain("make migrate");
    } finally {
      await database.close();
    }
  });

  it("applies every migration once and then passes the boot check", async () => {
    const database = await createTestDatabase(inject("pgAdminUrl"), { migrated: false });
    try {
      expect(await runMigrations(database.url)).toEqual({ applied: migrationCount });
      expect(await runMigrations(database.url)).toEqual({ applied: 0 });
      await expect(assertMigrationsApplied(database.db)).resolves.toBeUndefined();
    } finally {
      await database.close();
    }
  });

  it("serializes concurrent runs so each migration is applied exactly once", async () => {
    const database = await createTestDatabase(inject("pgAdminUrl"), { migrated: false });
    try {
      const results = await Promise.all([1, 2, 3, 4].map(() => runMigrations(database.url)));
      expect(results.reduce((sum, r) => sum + r.applied, 0)).toBe(migrationCount);
      await expect(assertMigrationsApplied(database.db)).resolves.toBeUndefined();
    } finally {
      await database.close();
    }
  });
});
