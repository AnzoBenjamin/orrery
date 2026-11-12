import { fileURLToPath } from "node:url";
import { sql } from "drizzle-orm";
import { readMigrationFiles } from "drizzle-orm/migrator";
import { drizzle } from "drizzle-orm/node-postgres";
import { migrate } from "drizzle-orm/node-postgres/migrator";
import pg from "pg";
import type { Db } from "./client.ts";
import * as schema from "./schema/index.ts";

export const migrationsFolder = fileURLToPath(new URL("../migrations", import.meta.url));

const MIGRATIONS_SCHEMA = "drizzle";
const MIGRATIONS_TABLE = "__drizzle_migrations";
/** Arbitrary constant naming the migration advisory lock ("orrery" in ASCII). */
const MIGRATION_LOCK_KEY = 0x6f72726572797n;

/**
 * Applies pending migrations over one dedicated connection. A session-level advisory lock on that
 * connection serializes concurrent runs (two deploys, or a deploy and a developer), so each
 * migration runs exactly once.
 */
export async function runMigrations(connectionString: string): Promise<{ applied: number }> {
  const client = new pg.Client({ connectionString, application_name: "orrery-migrate" });
  await client.connect();
  try {
    const db = drizzle(client, { schema });
    await client.query("select pg_advisory_lock($1)", [MIGRATION_LOCK_KEY.toString()]);
    const before = await appliedHashes(db);
    await migrate(db, {
      migrationsFolder,
      migrationsSchema: MIGRATIONS_SCHEMA,
      migrationsTable: MIGRATIONS_TABLE,
    });
    const after = await appliedHashes(db);
    return { applied: after.size - before.size };
  } finally {
    await client.end();
  }
}

export class MigrationsPendingError extends Error {
  readonly pending: readonly string[];

  constructor(pending: readonly string[]) {
    super(
      `The database is missing ${pending.length} migration(s): ${pending.join(", ")}. ` +
        "Run `make migrate` (or the deploy migrate step) before starting this process.",
    );
    this.name = "MigrationsPendingError";
    this.pending = pending;
  }
}

/**
 * Boot check for the web app and worker: throws `MigrationsPendingError` when any migration in
 * this build is not recorded in the database. Migrations the database has but this build lacks
 * are allowed, so `kamal rollback` to the previous release still starts.
 */
export async function assertMigrationsApplied(db: Db): Promise<void> {
  const applied = await appliedHashes(db);
  const local = readMigrationFiles({ migrationsFolder });
  const journal = await import("../migrations/meta/_journal.json", { with: { type: "json" } });
  const pending = local
    .map((m, i) => ({ hash: m.hash, tag: journal.default.entries[i]?.tag ?? `#${i}` }))
    .filter((m) => !applied.has(m.hash))
    .map((m) => m.tag);
  if (pending.length > 0) throw new MigrationsPendingError(pending);
}

async function appliedHashes(db: Pick<Db, "execute">): Promise<Set<string>> {
  const exists = await db.execute<{ present: boolean }>(
    sql`select to_regclass(${`${MIGRATIONS_SCHEMA}.${MIGRATIONS_TABLE}`}) is not null as present`,
  );
  if (!exists.rows[0]?.present) return new Set();
  const rows = await db.execute<{ hash: string }>(
    sql`select hash from ${sql.identifier(MIGRATIONS_SCHEMA)}.${sql.identifier(MIGRATIONS_TABLE)}`,
  );
  return new Set(rows.rows.map((r) => r.hash));
}
