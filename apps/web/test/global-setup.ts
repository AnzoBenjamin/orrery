import { startTestPostgres } from "@orrery/db/testing";
import type { TestProject } from "vitest/node";

declare module "vitest" {
  export interface ProvidedContext {
    pgAdminUrl: string;
  }
}

export default async function setup(project: TestProject) {
  const postgres = await startTestPostgres();
  project.provide("pgAdminUrl", postgres.adminUrl);
  return () => postgres.stop();
}
