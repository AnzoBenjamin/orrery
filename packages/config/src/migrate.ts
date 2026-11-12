import { createEnv } from "@t3-oss/env-core";
import type { z } from "zod";
import { type EnvSource, envOptions, orExit } from "./load.ts";
import { database } from "./parts.ts";

export const migrateShape = { ...database };

export type MigrateEnv = Readonly<z.output<z.ZodObject<typeof migrateShape>>>;

export function parseMigrateEnv(source: EnvSource): MigrateEnv {
  return createEnv({ server: migrateShape, ...envOptions("migrate", source) });
}

export function loadMigrateEnv(source: EnvSource = process.env): MigrateEnv {
  return orExit(() => parseMigrateEnv(source));
}
