import { PgBoss } from "pg-boss";

/** pg-boss keeps its tables in this schema, apart from the application's. */
export const PG_BOSS_SCHEMA = "pgboss";

/**
 * Installs or upgrades the pg-boss schema. Runs in the deploy migrate step (`make migrate`), so
 * web and worker processes never alter the database at startup.
 */
export async function migrateJobSchema(connectionString: string): Promise<void> {
  const boss = new PgBoss({
    connectionString,
    schema: PG_BOSS_SCHEMA,
    max: 1,
    application_name: "orrery-migrate",
    migrate: true,
    createSchema: true,
    supervise: false,
    schedule: false,
  });
  await boss.start();
  await boss.stop({ graceful: false });
}

/**
 * A publish-only client for the web app: no maintenance, no cron, no schema changes, and a small
 * dedicated pool.
 */
export function createProducer(connectionString: string): PgBoss {
  return new PgBoss({
    connectionString,
    schema: PG_BOSS_SCHEMA,
    max: 2,
    application_name: "orrery-web-jobs",
    migrate: false,
    createSchema: false,
    supervise: false,
    schedule: false,
  });
}

/** The worker's client: runs handlers, supervision (expiry, retention), and cron schedules. */
export function createWorkerBoss(connectionString: string): PgBoss {
  return new PgBoss({
    connectionString,
    schema: PG_BOSS_SCHEMA,
    max: 4,
    application_name: "orrery-worker",
    migrate: false,
    createSchema: false,
    supervise: true,
    schedule: true,
  });
}
