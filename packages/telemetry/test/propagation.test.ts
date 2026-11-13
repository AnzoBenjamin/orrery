import { context, propagation, trace } from "@opentelemetry/api";
import { AsyncLocalStorageContextManager } from "@opentelemetry/context-async-hooks";
import { W3CTraceContextPropagator } from "@opentelemetry/core";
import {
  InMemorySpanExporter,
  SimpleSpanProcessor,
  TracerProvider,
} from "@opentelemetry/sdk-trace";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { currentTraceId, currentTraceparent, inSpan, reportError } from "../src/index.ts";

const exporter = new InMemorySpanExporter();
let provider: TracerProvider;

beforeAll(() => {
  provider = new TracerProvider({ spanProcessors: [new SimpleSpanProcessor({ exporter })] });
  trace.setGlobalTracerProvider(provider);
  context.setGlobalContextManager(new AsyncLocalStorageContextManager().enable());
  propagation.setGlobalPropagator(new W3CTraceContextPropagator());
});
afterAll(async () => {
  await provider.shutdown();
});

describe("trace propagation", () => {
  it("a job continues the trace of the request that enqueued it", async () => {
    exporter.reset();
    // The web request: its traceparent goes into the job payload.
    const traceparent = await inSpan("POST footage.upload.complete", undefined, {}, async () => {
      const tp = currentTraceparent();
      expect(tp).toMatch(/^00-[0-9a-f]{32}-[0-9a-f]{16}-01$/);
      return tp;
    });
    // The worker: the job span joins that trace.
    await inSpan("job footage.probe", traceparent, { "job.queue": "footage.probe" }, async () => {
      expect(currentTraceId()).toBe(traceparent?.split("-")[1]);
    });
    const spans = exporter.getFinishedSpans();
    expect(spans.map((s) => s.name)).toEqual(["POST footage.upload.complete", "job footage.probe"]);
    const [request, job] = spans;
    expect(job?.spanContext().traceId).toBe(request?.spanContext().traceId);
    expect(job?.parentSpanContext?.spanId).toBe(request?.spanContext().spanId);
  });

  it("records a failure on the span and rethrows it", async () => {
    exporter.reset();
    await expect(
      inSpan("job objects.delete", undefined, {}, async () => {
        throw new Error("storage unreachable");
      }),
    ).rejects.toThrow("storage unreachable");
    const [span] = exporter.getFinishedSpans();
    expect(span?.status.code).toBe(2);
    expect(span?.events.map((e) => e.name)).toContain("exception");
  });

  it("gives a short reference even with error reporting off", () => {
    expect(reportError(new Error("x"))).toMatch(/^[0-9a-f]{8}$/);
  });
});
