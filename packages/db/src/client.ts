import type { ExtractTablesWithRelations } from "drizzle-orm";
import type { NodePgQueryResultHKT } from "drizzle-orm/node-postgres";
import { drizzle, type NodePgDatabase } from "drizzle-orm/node-postgres";
import type { PgTransaction } from "drizzle-orm/pg-core";
import pg from "pg";
import * as schema from "./schema/index.ts";

export type Schema = typeof schema;
export type Db = NodePgDatabase<Schema>;
export type Tx = PgTransaction<NodePgQueryResultHKT, Schema, ExtractTablesWithRelations<Schema>>;
/** Query modules accept either the pool-backed database or an open transaction. */
export type Executor = Db | Tx;

export interface DbOptions {
  connectionString: string;
  /** Pool size. The VPS budget leaves room for about 20 connections per process (tech.md). */
  max?: number;
  applicationName: string;
}

export interface DbHandle {
  db: Db;
  pool: pg.Pool;
  close(): Promise<void>;
}

export function createDb({ connectionString, max = 10, applicationName }: DbOptions): DbHandle {
  const pool = new pg.Pool({
    connectionString,
    max,
    application_name: applicationName,
    idleTimeoutMillis: 30_000,
    connectionTimeoutMillis: 5_000,
  });
  const db = drizzle(pool, { schema });
  return { db, pool, close: () => pool.end() };
}
