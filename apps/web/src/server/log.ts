import pino from "pino";

/**
 * Structured JSON logs (requirement 11.3). OpenTelemetry's pino instrumentation adds trace_id
 * and span_id to each line written inside a traced request.
 */
export const log = pino({
  level: process.env.LOG_LEVEL ?? "info",
  base: { service: "orrery-web" },
  timestamp: pino.stdTimeFunctions.isoTime,
  redact: { paths: ["*.password", "*.token", "*.url", "*.cookie"], censor: "[redacted]" },
});
