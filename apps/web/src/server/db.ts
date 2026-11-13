import {
  assertMigrationsApplied,
  createDb,
  createListener,
  type DbHandle,
  type Listener,
} from "@orrery/db";
import { serverEnv } from "./env.ts";

let handle: DbHandle | undefined;
let ready: Promise<void> | undefined;

/** The web app's connection pool, created on first use. */
export function database(): DbHandle {
  handle ??= createDb({
    connectionString: serverEnv().DATABASE_URL,
    max: 10,
    applicationName: "orrery-web",
  });
  return handle;
}

/**
 * Resolves once the database is known to have every migration this build expects. In production
 * a failure stops the process (requirement 3.2); elsewhere it is reported on each request so a
 * developer sees "run make migrate" instead of a crash loop.
 */
export function databaseReady(): Promise<void> {
  ready ??= assertMigrationsApplied(database().db).catch((error: unknown) => {
    if (serverEnv().NODE_ENV === "production") {
      process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
      process.exit(1);
    }
    ready = undefined;
    throw error;
  });
  return ready;
}

let listener: Listener | undefined;

/** The process's one LISTEN connection, shared by every open event stream. */
export function databaseListener(): Listener {
  listener ??= createListener({
    connectionString: serverEnv().DATABASE_URL,
    applicationName: "orrery-web-listen",
    onError: (error) =>
      process.stderr.write(
        `${JSON.stringify({ level: "warn", msg: "listen connection lost", error: String(error) })}\n`,
      ),
  });
  return listener;
}
