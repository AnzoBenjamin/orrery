import { createProducer } from "@orrery/jobs";
import type { PgBoss } from "pg-boss";
import { serverEnv } from "./env.ts";

let started: Promise<PgBoss> | undefined;

/** Publish-only pg-boss client, started on first use. */
export function jobProducer(): Promise<PgBoss> {
  started ??= (async () => {
    const boss = createProducer(serverEnv().DATABASE_URL);
    await boss.start();
    return boss;
  })();
  return started;
}
