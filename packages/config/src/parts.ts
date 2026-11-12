import { z } from "zod";

/**
 * Shared variable groups. Messages are set explicitly where Zod's default could include the input,
 * so a failing value is never printed.
 */

const url = (protocols: RegExp, label: string) =>
  z.url({ protocol: protocols, error: `must be a ${label} URL` });

export const httpUrl = url(/^https?$/, "http(s)");

export const runtime = {
  NODE_ENV: z.enum(["development", "test", "production"]).default("development"),
  LOG_LEVEL: z.enum(["fatal", "error", "warn", "info", "debug", "trace"]).default("info"),
};

export const database = {
  DATABASE_URL: url(/^postgres(ql)?$/, "postgres://"),
};

export const objectStorage = {
  /** Endpoint the server uses to reach Garage (inside Docker: http://garage:3900). */
  S3_ENDPOINT: httpUrl,
  /** Endpoint browsers use. Presigned URLs are signed for this host, so it must be the public one. */
  S3_PUBLIC_ENDPOINT: httpUrl,
  S3_REGION: z.string().min(1, "must not be empty"),
  S3_BUCKET: z
    .string()
    .regex(/^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$/, "must be a valid S3 bucket name"),
  S3_ACCESS_KEY_ID: z.string().min(1, "must not be empty"),
  S3_SECRET_ACCESS_KEY: z.string().min(1, "must not be empty"),
};

export const mail = {
  SMTP_HOST: z.string().min(1, "must not be empty"),
  SMTP_PORT: z.coerce
    .number({ error: "must be a port number" })
    .int("must be a port number")
    .min(1, "must be a port number")
    .max(65535, "must be a port number"),
  SMTP_SECURE: z.stringbool({ error: 'must be "true" or "false"' }).default(false),
  SMTP_USER: z.string().min(1, "must not be empty").optional(),
  SMTP_PASSWORD: z.string().min(1, "must not be empty").optional(),
  MAIL_FROM: z.string().min(3, "must be a sender such as Orrery <mail@example.org>"),
};

export const telemetry = {
  /** OTLP/HTTP collector endpoint. Required in production; telemetry export is off without it. */
  OTEL_EXPORTER_OTLP_ENDPOINT: httpUrl.optional(),
  /** GlitchTip DSN for the Sentry SDK. Required in production; error reporting is off without it. */
  SENTRY_DSN: httpUrl.optional(),
};

/** Adds an issue for each listed variable that is unset in production. */
export function requireInProduction(
  env: Record<string, unknown>,
  ctx: z.RefinementCtx,
  keys: readonly string[],
): void {
  if (env.NODE_ENV !== "production") return;
  for (const key of keys) {
    if (env[key] === undefined) {
      ctx.addIssue({ code: "custom", path: [key], message: "is required in production" });
    }
  }
}

/** Adds an issue when only one variable of a pair is set. */
export function requireTogether(
  env: Record<string, unknown>,
  ctx: z.RefinementCtx,
  a: string,
  b: string,
): void {
  const hasA = env[a] !== undefined;
  const hasB = env[b] !== undefined;
  if (hasA !== hasB) {
    const missing = hasA ? b : a;
    ctx.addIssue({
      code: "custom",
      path: [missing],
      message: `must be set together with ${hasA ? a : b}`,
    });
  }
}
