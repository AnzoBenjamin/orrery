import type { TestProject } from "vitest/node";
import { startTestPostgres } from "../src/testing/index.ts";

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
