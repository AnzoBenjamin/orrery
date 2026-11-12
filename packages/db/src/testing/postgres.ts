import { PostgreSqlContainer, type StartedPostgreSqlContainer } from "@testcontainers/postgresql";
import pg from "pg";
import { createDb, type DbHandle } from "../client.ts";
import { newId } from "../ids.ts";
import { runMigrations } from "../migrate.ts";

/** Same image as infra/compose.yaml and production. */
export const POSTGRES_IMAGE =
  "postgres:18.6-trixie@sha256:e3d24f6906d0760bf4da0dae872415391ededefad23fd471c47dc53b0ddf3c42";

const TEMPLATE_DATABASE = "orrery_template";

export interface TestPostgres {
  /** Connection string for the server's maintenance database, used to create test databases. */
  adminUrl: string;
  stop(): Promise<void>;
}

/**
 * Starts a real Postgres 18 in Docker and migrates a template database. Call once per test run
 * (Vitest globalSetup); each test file then clones the template with `createTestDatabase`.
 */
export async function startTestPostgres(): Promise<TestPostgres> {
  const container: StartedPostgreSqlContainer = await new PostgreSqlContainer(POSTGRES_IMAGE)
    .withDatabase("postgres")
    .start();
  const adminUrl = container.getConnectionUri();
  await adminQuery(adminUrl, `create database ${TEMPLATE_DATABASE}`);
  await runMigrations(withDatabase(adminUrl, TEMPLATE_DATABASE));
  return {
    adminUrl,
    stop: async () => {
      await container.stop();
    },
  };
}

export interface TestDatabase extends DbHandle {
  url: string;
}

/**
 * A fresh database, dropped by `close()`. By default it is cloned from the migrated template;
 * `{ migrated: false }` gives an empty one for testing the migrator itself.
 */
export async function createTestDatabase(
  adminUrl: string,
  options: { migrated?: boolean } = {},
): Promise<TestDatabase> {
  const name = `orrery_test_${newId().replaceAll("-", "")}`;
  const template = options.migrated === false ? "template0" : TEMPLATE_DATABASE;
  await adminQuery(adminUrl, `create database ${name} template ${template}`);
  const url = withDatabase(adminUrl, name);
  const handle = createDb({ connectionString: url, max: 5, applicationName: "orrery-test" });
  return {
    ...handle,
    url,
    close: async () => {
      await handle.close();
      await adminQuery(adminUrl, `drop database if exists ${name} with (force)`);
    },
  };
}

function withDatabase(url: string, database: string): string {
  const parsed = new URL(url);
  parsed.pathname = `/${database}`;
  return parsed.toString();
}

async function adminQuery(adminUrl: string, statement: string): Promise<void> {
  const client = new pg.Client({ connectionString: adminUrl });
  await client.connect();
  try {
    await client.query(statement);
  } finally {
    await client.end();
  }
}
