import { createEnv } from "@t3-oss/env-core";
import { z } from "zod";
import { type EnvSource, envOptions, orExit } from "./load.ts";
import {
  database,
  httpUrl,
  objectStorage,
  requireInProduction,
  requireTogether,
  runtime,
  telemetry,
} from "./parts.ts";

/** Server-side variables of the web app. None of these reach the browser. */
export const webServerShape = {
  ...runtime,
  ...database,
  ...objectStorage,
  ...telemetry,
  /** Public origin of the web app, for example https://orrery.example. */
  BETTER_AUTH_URL: httpUrl,
  BETTER_AUTH_SECRET: z.string().min(32, "must be at least 32 characters"),
  /**
   * Multiplies the auth rate limits. The local stack raises it so the end-to-end suite, which
   * signs up many accounts from one address, is not throttled. Must be 1 in production.
   */
  AUTH_RATE_LIMIT_SCALE: z.coerce
    .number({ error: "must be a whole number from 1 to 1000" })
    .int("must be a whole number from 1 to 1000")
    .min(1, "must be a whole number from 1 to 1000")
    .max(1000, "must be a whole number from 1 to 1000")
    .default(1),
  GITHUB_CLIENT_ID: z.string().min(1, "must not be empty").optional(),
  GITHUB_CLIENT_SECRET: z.string().min(1, "must not be empty").optional(),
  GOOGLE_CLIENT_ID: z.string().min(1, "must not be empty").optional(),
  GOOGLE_CLIENT_SECRET: z.string().min(1, "must not be empty").optional(),
};

function refineWeb(env: Record<string, unknown>, ctx: z.RefinementCtx): void {
  requireTogether(env, ctx, "GITHUB_CLIENT_ID", "GITHUB_CLIENT_SECRET");
  requireTogether(env, ctx, "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET");
  requireInProduction(env, ctx, [
    "GITHUB_CLIENT_ID",
    "GITHUB_CLIENT_SECRET",
    "GOOGLE_CLIENT_ID",
    "GOOGLE_CLIENT_SECRET",
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "SENTRY_DSN",
  ]);
  if (env.NODE_ENV === "production" && env.AUTH_RATE_LIMIT_SCALE !== 1) {
    ctx.addIssue({
      code: "custom",
      path: ["AUTH_RATE_LIMIT_SCALE"],
      message: "must be 1 in production",
    });
  }
  if (env.NODE_ENV === "production" && typeof env.BETTER_AUTH_URL === "string") {
    if (!env.BETTER_AUTH_URL.startsWith("https://")) {
      ctx.addIssue({
        code: "custom",
        path: ["BETTER_AUTH_URL"],
        message: "must use https in production",
      });
    }
  }
}

export type WebServerEnv = Readonly<z.output<z.ZodObject<typeof webServerShape>>>;

export function parseWebServerEnv(source: EnvSource): WebServerEnv {
  return createEnv({
    server: webServerShape,
    createFinalSchema: (shape) => z.object(shape).superRefine(refineWeb),
    ...envOptions("web", source),
  });
}

export function loadWebServerEnv(source: EnvSource = process.env): WebServerEnv {
  return orExit(() => parseWebServerEnv(source));
}

/**
 * Variables the browser may see. Only names with the PUBLIC_ prefix are allowed here, and the web
 * app's bundler is configured to expose that prefix only.
 */
export const webPublicShape = {
  PUBLIC_SENTRY_DSN: httpUrl.optional(),
};

export type WebPublicEnv = Readonly<z.output<z.ZodObject<typeof webPublicShape>>>;

export function parseWebPublicEnv(source: EnvSource): WebPublicEnv {
  for (const key of Object.keys(webPublicShape)) {
    if (!key.startsWith("PUBLIC_")) {
      throw new Error(`webPublicShape key ${key} lacks the PUBLIC_ prefix`);
    }
  }
  return createEnv({ server: webPublicShape, ...envOptions("web (public)", source) });
}
