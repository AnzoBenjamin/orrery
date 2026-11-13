import fc from "fast-check";

/** Random lowercase hex of exactly `length` characters. */
export const hex = (length: number) =>
  fc.string({ unit: fc.constantFrom(..."0123456789abcdef"), minLength: length, maxLength: length });

const host = fc.constantFrom("localhost", "garage", "engine", "orrery.example", "10.0.0.7");
const port = fc.integer({ min: 1, max: 65535 });
const httpUrl = fc
  .tuple(fc.constantFrom("http", "https"), host, port)
  .map(([scheme, h, p]) => `${scheme}://${h}:${p}`);
const httpsUrl = fc.tuple(host, port).map(([h, p]) => `https://${h}:${p}`);

/** Variables whose values must never appear in error output. */
export const SECRET_KEYS = [
  "DATABASE_URL",
  "S3_SECRET_ACCESS_KEY",
  "SMTP_PASSWORD",
  "BETTER_AUTH_SECRET",
  "GITHUB_CLIENT_SECRET",
  "GOOGLE_CLIENT_SECRET",
  "ENGINE_SERVICE_TOKEN",
] as const;

const storage = fc.record({
  DATABASE_URL: hex(32).map((pw) => `postgres://orrery:${pw}@postgres:5432/orrery`),
  S3_ENDPOINT: httpUrl,
  S3_PUBLIC_ENDPOINT: httpUrl,
  S3_REGION: fc.constantFrom("garage", "eu-west-1"),
  S3_BUCKET: fc.constantFrom("orrery", "orrery-test", "footage.archive"),
  S3_ACCESS_KEY_ID: hex(24).map((h) => `GK${h}`),
  S3_SECRET_ACCESS_KEY: hex(64),
});

export const validWorkerEnv = fc
  .tuple(
    storage,
    fc.record({
      NODE_ENV: fc.constantFrom("development", "test"),
      SMTP_HOST: host,
      SMTP_PORT: port.map(String),
      SMTP_SECURE: fc.constantFrom("true", "false"),
      SMTP_USER: fc.constant("orrery"),
      SMTP_PASSWORD: hex(40),
      MAIL_FROM: fc.constant("Orrery <mail@orrery.example>"),
      APP_URL: httpUrl,
      WORKER_HEALTH_PORT: port.map(String),
      ENGINE_URL: httpUrl,
      ENGINE_SERVICE_TOKEN: hex(64),
    }),
  )
  .map(([a, b]): Record<string, string> => ({ ...a, ...b }));

export const validWebEnv = fc
  .tuple(
    storage,
    fc.record({
      NODE_ENV: fc.constantFrom("development", "test"),
      BETTER_AUTH_URL: httpUrl,
      BETTER_AUTH_SECRET: hex(64),
      GITHUB_CLIENT_ID: hex(20),
      GITHUB_CLIENT_SECRET: hex(40),
      GOOGLE_CLIENT_ID: hex(20),
      GOOGLE_CLIENT_SECRET: hex(40),
    }),
  )
  .map(([a, b]): Record<string, string> => ({ ...a, ...b }));

export const validProductionWebEnv = fc.tuple(validWebEnv, httpsUrl, httpUrl, httpUrl).map(
  ([env, appUrl, otel, dsn]): Record<string, string> => ({
    ...env,
    NODE_ENV: "production",
    BETTER_AUTH_URL: appUrl,
    OTEL_EXPORTER_OTLP_ENDPOINT: otel,
    SENTRY_DSN: dsn,
  }),
);

/**
 * Invalid values per variable. Secret variables get long random values, so a value leaking into
 * an error message is detectable without false positives from the message text itself.
 */
export const invalidValue: Record<string, fc.Arbitrary<string>> = {
  DATABASE_URL: hex(32).map((pw) => `mysql://orrery:${pw}@db/orrery`),
  S3_ENDPOINT: hex(16).map((h) => `ftp://${h}`),
  S3_PUBLIC_ENDPOINT: hex(16).map((h) => `not a url ${h}`),
  S3_BUCKET: hex(12).map((h) => `Bad_Bucket_${h}`),
  S3_SECRET_ACCESS_KEY: fc.constant(""),
  SMTP_PORT: fc.constantFrom("0", "70000", "smtp", "25.5"),
  SMTP_SECURE: fc.constantFrom("yes please", "maybe"),
  SMTP_PASSWORD: fc.constant(""),
  APP_URL: hex(16).map((h) => `javascript:${h}`),
  WORKER_HEALTH_PORT: fc.constantFrom("0", "65536", "http"),
  ENGINE_URL: hex(16).map((h) => `engine-${h}`),
  ENGINE_SERVICE_TOKEN: fc.integer({ min: 12, max: 31 }).chain((n) => hex(n)),
  STORAGE_QUOTA_BYTES: fc.constantFrom("lots", "-1", "1000", "1.5e9x"),
  BETTER_AUTH_URL: hex(16).map((h) => `file:///${h}`),
  BETTER_AUTH_SECRET: fc.integer({ min: 12, max: 31 }).chain((n) => hex(n)),
  NODE_ENV: fc.constantFrom("staging", "prod"),
};
