/**
 * `make migrate` and the deploy migrate step. Applies pending migrations, then verifies that none
 * remain. Exit code 1 on any failure.
 */
import { loadMigrateEnv } from "@orrery/config/migrate";
import { createDb } from "./client.ts";
import { assertMigrationsApplied, runMigrations } from "./migrate.ts";

const env = loadMigrateEnv();
const handle = createDb({
  connectionString: env.DATABASE_URL,
  max: 1,
  applicationName: "orrery-migrate",
});
try {
  const { applied } = await runMigrations(env.DATABASE_URL);
  await assertMigrationsApplied(handle.db);
  process.stdout.write(`migrate: ${applied} migration(s) applied, database is current\n`);
} catch (error) {
  process.stderr.write(
    `migrate: failed: ${error instanceof Error ? error.message : String(error)}\n`,
  );
  process.exitCode = 1;
} finally {
  await handle.close();
}
