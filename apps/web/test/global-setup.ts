import { startTestPostgres } from "@orrery/db/testing";
import type { StorageConfig } from "@orrery/storage";
import { startTestGarage } from "@orrery/storage/testing";
import type { TestProject } from "vitest/node";

declare module "vitest" {
  export interface ProvidedContext {
    pgAdminUrl: string;
    garage: StorageConfig;
  }
}

export default async function setup(project: TestProject) {
  const [postgres, garage] = await Promise.all([startTestPostgres(), startTestGarage()]);
  project.provide("pgAdminUrl", postgres.adminUrl);
  project.provide("garage", garage.config);
  return async () => {
    await Promise.all([postgres.stop(), garage.stop()]);
  };
}
