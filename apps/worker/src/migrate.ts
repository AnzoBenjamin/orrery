/**
 * The deploy migrate step and `make migrate`: applies Drizzle migrations and installs or upgrades
 * the pg-boss schema, then verifies nothing is pending. Runs once per deployment before new web
 * and worker processes start (requirement 3.3). Exit code 1 on failure.
 */
import { loadMigrateEnv } from "@orrery/config/migrate";
import { assertMigrationsApplied, createDb, runMigrations } from "@orrery/db";
import { migrateJobSchema } from "@orrery/jobs";

const env = loadMigrateEnv();
const handle = createDb({
  connectionString: env.DATABASE_URL,
  max: 1,
  applicationName: "orrery-migrate",
});
try {
  const { applied } = await runMigrations(env.DATABASE_URL);
  await migrateJobSchema(env.DATABASE_URL);
  await assertMigrationsApplied(handle.db);
  process.stdout.write(
    `migrate: ${applied} migration(s) applied, job schema current, database is current\n`,
  );
} catch (error) {
  process.stderr.write(
    `migrate: failed: ${error instanceof Error ? error.message : String(error)}\n`,
  );
  process.exitCode = 1;
} finally {
  await handle.close();
}
