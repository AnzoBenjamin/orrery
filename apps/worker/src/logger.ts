import pino from "pino";

/** Structured JSON logs. Trace ids are added once OpenTelemetry lands (task 8.1). */
export function createLogger(level: string) {
  return pino({
    level,
    base: { service: "orrery-worker" },
    timestamp: pino.stdTimeFunctions.isoTime,
    redact: { paths: ["*.password", "*.token", "*.url", "message.url"], censor: "[redacted]" },
  });
}

export type Logger = ReturnType<typeof createLogger>;
