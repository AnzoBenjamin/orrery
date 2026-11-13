import type { TestProject } from "vitest/node";
import type { StorageConfig } from "../src/client.ts";
import { startTestGarage } from "../src/testing.ts";

declare module "vitest" {
  export interface ProvidedContext {
    garage: StorageConfig;
  }
}

export default async function setup(project: TestProject) {
  const garage = await startTestGarage();
  project.provide("garage", garage.config);
  return () => garage.stop();
}
