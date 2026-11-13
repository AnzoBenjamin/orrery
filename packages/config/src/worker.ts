import { createEnv } from "@t3-oss/env-core";
import { z } from "zod";
import { type EnvSource, envOptions, orExit } from "./load.ts";
import {
  database,
  httpUrl,
  mail,
  objectStorage,
  requireInProduction,
  requireTogether,
  runtime,
  telemetry,
} from "./parts.ts";

export const workerShape = {
  ...runtime,
  ...database,
  ...objectStorage,
  ...mail,
  ...telemetry,
  /** Public origin of the web app, used in email links and as the base of engine callback URLs. */
  APP_URL: httpUrl,
  /** Internal URL of the engine service. Only the worker calls it. */
  ENGINE_URL: httpUrl,
  /** Bearer token the engine expects from the worker. */
  ENGINE_SERVICE_TOKEN: z.string().min(32, "must be at least 32 characters"),
  /** Port of the internal health endpoint (Compose and Kamal health checks). Not published. */
  WORKER_HEALTH_PORT: z.coerce
    .number({ error: "must be a port number" })
    .int("must be a port number")
    .min(1, "must be a port number")
    .max(65535, "must be a port number")
    .default(9090),
};

function refineWorker(env: Record<string, unknown>, ctx: z.RefinementCtx): void {
  requireTogether(env, ctx, "SMTP_USER", "SMTP_PASSWORD");
  requireInProduction(env, ctx, ["OTEL_EXPORTER_OTLP_ENDPOINT", "SENTRY_DSN"]);
}

export type WorkerEnv = Readonly<z.output<z.ZodObject<typeof workerShape>>>;

export function parseWorkerEnv(source: EnvSource): WorkerEnv {
  return createEnv({
    server: workerShape,
    createFinalSchema: (shape) => z.object(shape).superRefine(refineWorker),
    ...envOptions("worker", source),
  });
}

export function loadWorkerEnv(source: EnvSource = process.env): WorkerEnv {
  return orExit(() => parseWorkerEnv(source));
}
