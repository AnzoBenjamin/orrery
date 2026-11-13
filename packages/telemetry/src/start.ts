import { OTLPTraceExporter } from "@opentelemetry/exporter-trace-otlp-proto";
import { HttpInstrumentation } from "@opentelemetry/instrumentation-http";
import { PgInstrumentation } from "@opentelemetry/instrumentation-pg";
import { PinoInstrumentation } from "@opentelemetry/instrumentation-pino";
import { UndiciInstrumentation } from "@opentelemetry/instrumentation-undici";
import { resourceFromAttributes } from "@opentelemetry/resources";
import { NodeSDK } from "@opentelemetry/sdk-node";
import { ATTR_SERVICE_NAME, ATTR_SERVICE_VERSION } from "@opentelemetry/semantic-conventions";
import * as Sentry from "@sentry/node";

export interface TelemetryOptions {
  serviceName: string;
  /** Release identifier (the deployed commit). */
  release?: string | undefined;
  environment: string;
  /** OTLP/HTTP collector base URL; tracing is off without it. */
  otlpEndpoint?: string | undefined;
  /** GlitchTip DSN; error reporting is off without it. */
  sentryDsn?: string | undefined;
}

/**
 * Starts tracing and error reporting. Call before the application imports `pg` or `http`, which
 * is what `@orrery/telemetry/register` (loaded with `node --import`) does.
 */
export function startTelemetry(options: TelemetryOptions): { shutdown(): Promise<void> } {
  let sdk: NodeSDK | undefined;
  if (options.otlpEndpoint) {
    sdk = new NodeSDK({
      resource: resourceFromAttributes({
        [ATTR_SERVICE_NAME]: options.serviceName,
        ...(options.release ? { [ATTR_SERVICE_VERSION]: options.release } : {}),
        "deployment.environment.name": options.environment,
      }),
      traceExporter: new OTLPTraceExporter({
        url: `${options.otlpEndpoint.replace(/\/$/, "")}/v1/traces`,
      }),
      instrumentations: [
        new HttpInstrumentation({
          // Health checks run every few seconds and say nothing about user actions.
          ignoreIncomingRequestHook: (req) => req.url === "/health" || req.url === "/api/health",
        }),
        new UndiciInstrumentation(),
        new PgInstrumentation({ enhancedDatabaseReporting: false }),
        // Adds trace_id and span_id to every pino log line (requirement 11.3).
        new PinoInstrumentation(),
      ],
    });
    sdk.start();
  }
  if (options.sentryDsn) {
    Sentry.init({
      dsn: options.sentryDsn,
      release: options.release,
      environment: options.environment,
      // Errors only: traces go through OpenTelemetry. No IPs, cookies, or bodies.
      dataCollection: {
        userInfo: false,
        cookies: false,
        httpHeaders: false,
        httpBodies: [],
        // Share tokens and signed URLs travel in query strings.
        urlQueryParams: false,
      },
      enableOpenTelemetrySetup: false,
    });
  }
  return {
    async shutdown() {
      await Promise.allSettled([sdk?.shutdown(), Sentry.close(2000)]);
    },
  };
}
