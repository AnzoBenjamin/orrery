/**
 * Schema version migrations.
 *
 * When the schema version changes, add a migration function here that transforms
 * a mechanism from the old version to the new version.
 */
import type { Mechanism } from "./mechanism.ts";

export type MigrationFn = (old: unknown) => Mechanism;

/**
 * Registry of migrations keyed by source schema version.
 *
 * To migrate from version N to the current version, apply migrations in sequence:
 * N → N+1 → N+2 → ... → current
 */
export const migrations: Record<number, MigrationFn> = {
  // When version 2 is added, the migration from 1 to 2 will go here:
  // 1: (old: MechanismV1) => MechanismV2 { ... }
};

/**
 * Migrate a mechanism from any earlier version to the current version.
 *
 * @param data - Mechanism data with a schemaVersion field
 * @returns Migrated mechanism at the current version (1)
 * @throws Error if the schema version is not supported or migrations are missing
 */
export function migrateToCurrentVersion(data: unknown): Mechanism {
  if (typeof data !== "object" || data === null) {
    throw new Error("Invalid mechanism data: expected an object");
  }

  if (!("schemaVersion" in data) || typeof data.schemaVersion !== "number") {
    throw new Error("Invalid mechanism data: missing or invalid schemaVersion");
  }

  const currentVersion = 1;
  const version = data.schemaVersion;

  if (version === currentVersion) {
    // Already at current version, validate and return
    return data as Mechanism;
  }

  if (version > currentVersion) {
    throw new Error(
      `Cannot migrate from future schema version ${version} to current version ${currentVersion}`,
    );
  }

  // Apply migrations in sequence
  let result: unknown = data;
  for (let v = version; v < currentVersion; v++) {
    const migrate = migrations[v];
    if (!migrate) {
      throw new Error(`Missing migration from schema version ${v} to ${v + 1}`);
    }
    result = migrate(result);
  }

  return result as Mechanism;
}
