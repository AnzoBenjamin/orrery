import { randomUUID } from "node:crypto";
import { context, propagation, type Span, SpanStatusCode, trace } from "@opentelemetry/api";
import * as Sentry from "@sentry/node";

/**
 * Tracing and error reporting for Node processes (requirement 11). OpenTelemetry carries traces
 * (OTLP to the collector); the Sentry SDK reports errors to GlitchTip. Both are off unless their
 * endpoint is configured, which production requires.
 */

const tracer = () => trace.getTracer("orrery");

/** The W3C traceparent of the active span, to put in job payloads and outgoing requests. */
export function currentTraceparent(): string | undefined {
  const carrier: Record<string, string> = {};
  propagation.inject(context.active(), carrier);
  return carrier.traceparent;
}

/**
 * Runs `fn` in a new span that continues the trace of `traceparent` (from a job payload or a
 * request header). Errors are recorded on the span and rethrown.
 */
export async function inSpan<T>(
  name: string,
  traceparent: string | null | undefined,
  attributes: Record<string, string | number | boolean>,
  fn: (span: Span) => Promise<T>,
): Promise<T> {
  const parent = traceparent
    ? propagation.extract(context.active(), { traceparent })
    : context.active();
  return tracer().startActiveSpan(name, { attributes }, parent, async (span) => {
    try {
      return await fn(span);
    } catch (error) {
      span.recordException(error instanceof Error ? error : String(error));
      span.setStatus({ code: SpanStatusCode.ERROR });
      throw error;
    } finally {
      span.end();
    }
  });
}

/** The trace id of the active span, for log lines and error references. */
export function currentTraceId(): string | undefined {
  const id = trace.getActiveSpan()?.spanContext().traceId;
  return id && !/^0+$/.test(id) ? id : undefined;
}

/**
 * Reports an unexpected error and returns a short reference the user can quote. With GlitchTip
 * configured the reference is the start of its event id, so support can look the event up.
 */
export function reportError(error: unknown, tags: Record<string, string> = {}): string {
  const eventId = Sentry.isInitialized()
    ? Sentry.captureException(error, { tags: { ...tags, trace_id: currentTraceId() ?? "none" } })
    : randomUUID();
  return eventId.replaceAll("-", "").slice(0, 8);
}

/** Associates errors reported in this request or job with a user, by id only (requirement 11.2). */
export function setErrorUser(userId: string | null): void {
  if (Sentry.isInitialized()) Sentry.setUser(userId ? { id: userId } : null);
}

export { startTelemetry, type TelemetryOptions } from "./start.ts";
