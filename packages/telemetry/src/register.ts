/**
 * Preload for Node processes: `node --import @orrery/telemetry/register app.js`. Installs the
 * ESM loader hook that lets OpenTelemetry instrument `pg` and `http`, then starts telemetry from
 * the environment (OTEL_SERVICE_NAME, OTEL_EXPORTER_OTLP_ENDPOINT, SENTRY_DSN, RELEASE). The
 * application validates the same variables again with its own schema.
 */
import { register } from "import-in-the-middle/register-hooks.mjs";
import { startTelemetry } from "./start.ts";

// Synchronous, in-thread loader hooks (Node 26), limited to the modules the instrumentations in
// start.ts patch, so the rest of the app is loaded untouched.
register({ include: ["pg", "pino", "undici", "http", "https", "node:http", "node:https"] });

const empty = (v: string | undefined) => (v && v.trim() !== "" ? v : undefined);

const telemetry = startTelemetry({
  serviceName: empty(process.env.OTEL_SERVICE_NAME) ?? "orrery",
  release: empty(process.env.RELEASE),
  environment: empty(process.env.NODE_ENV) ?? "development",
  otlpEndpoint: empty(process.env.OTEL_EXPORTER_OTLP_ENDPOINT),
  sentryDsn: empty(process.env.SENTRY_DSN),
});

for (const signal of ["SIGTERM", "SIGINT"] as const) {
  process.once(signal, () => {
    void telemetry.shutdown();
  });
}
