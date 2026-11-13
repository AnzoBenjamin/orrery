import {
  type Db,
  domainEventBody,
  type Listener,
  listDomainEventsAfter,
  specimenChannel,
} from "@orrery/db";

/** Comment line sent this often so proxies keep the connection open (design: 15 s). */
export const HEARTBEAT_MS = 15_000;
const BATCH = 200;

const encoder = new TextEncoder();

/**
 * Server-Sent Events for one specimen (requirement 8): every event after `afterId`, then new
 * ones as they are committed. NOTIFY only wakes the stream; events are always read from the
 * table in id order, so a reconnect with Last-Event-ID resumes exactly after the last event the
 * client saw (correctness property 4), even if notifications were missed.
 */
export function specimenEventStream(deps: {
  db: Db;
  listener: Listener;
  specimenId: string;
  afterId: number;
  signal: AbortSignal;
  heartbeatMs?: number;
}): ReadableStream<Uint8Array> {
  let lastId = deps.afterId;
  let unsubscribe: (() => Promise<void>) | undefined;
  let heartbeat: ReturnType<typeof setInterval> | undefined;
  let running: Promise<void> = Promise.resolve();
  let pendingWake = false;
  let finished = false;

  return new ReadableStream<Uint8Array>({
    async start(controller) {
      const finish = async () => {
        if (finished) return;
        finished = true;
        if (heartbeat) clearInterval(heartbeat);
        await unsubscribe?.();
        try {
          controller.close();
        } catch {
          // already closed by the client
        }
      };

      const pump = async () => {
        for (;;) {
          const events = await listDomainEventsAfter(deps.db, {
            specimenId: deps.specimenId,
            afterId: lastId,
            limit: BATCH,
          });
          for (const event of events) {
            lastId = event.id;
            const body = domainEventBody.safeParse({ type: event.type, payload: event.payload });
            if (!body.success) continue; // an event kind this release no longer emits
            controller.enqueue(
              encoder.encode(
                `id: ${event.id}\nevent: ${body.data.type}\ndata: ${JSON.stringify(body.data.payload)}\n\n`,
              ),
            );
          }
          if (events.length < BATCH) return;
        }
      };

      // Wakes are coalesced: one read at a time, and one more if anything arrived meanwhile.
      const wake = () => {
        if (finished) return;
        if (pendingWake) return;
        pendingWake = true;
        running = running
          .then(async () => {
            pendingWake = false;
            if (!finished) await pump();
          })
          .catch(async () => finish());
      };

      deps.signal.addEventListener("abort", () => void finish(), { once: true });
      controller.enqueue(encoder.encode("retry: 3000\n\n"));
      // Subscribe before the first read, so nothing committed in between is missed.
      unsubscribe = await deps.listener.subscribe(specimenChannel(deps.specimenId), wake);
      wake();
      heartbeat = setInterval(() => {
        if (!finished) controller.enqueue(encoder.encode(": heartbeat\n\n"));
      }, deps.heartbeatMs ?? HEARTBEAT_MS);
    },
    async cancel() {
      finished = true;
      if (heartbeat) clearInterval(heartbeat);
      await unsubscribe?.();
    },
  });
}

/** The id to resume after: Last-Event-ID from a reconnecting EventSource, else 0. */
export function resumeId(request: Request): number {
  const raw =
    request.headers.get("last-event-id") ?? new URL(request.url).searchParams.get("after");
  const id = raw && /^\d{1,15}$/.test(raw) ? Number(raw) : 0;
  return Number.isSafeInteger(id) ? id : 0;
}
