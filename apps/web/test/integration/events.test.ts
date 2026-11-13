import {
  appendDomainEvent,
  createListener,
  createSpecimen,
  type Listener,
  newId,
  schema,
} from "@orrery/db";
import fc from "fast-check";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { resumeId, specimenEventStream } from "../../src/server/specimen-events.ts";
import { withTestDatabase } from "./support.ts";

/**
 * Correctness property 4 (platform-foundation design): for any disconnect point, reconnecting
 * with Last-Event-ID yields exactly the events after that id. Validates requirement 8.2.
 */

const database = withTestDatabase();
let listener: Listener;

beforeAll(() => {
  listener = createListener({ connectionString: database().url, applicationName: "test-listen" });
});
afterAll(async () => {
  await listener.close();
});

async function newSpecimen() {
  const [owner] = await database()
    .db.insert(schema.user)
    .values({ name: "Events", email: `events-${newId()}@orrery.test` })
    .returning();
  if (!owner) throw new Error("no user");
  return createSpecimen(database().db, { ownerId: owner.id, title: "Escapement" });
}

function append(specimenId: string) {
  return appendDomainEvent(database().db, {
    specimenId,
    type: "footage.changed",
    payload: { footageId: newId(), status: "ready" },
  });
}

/** Reads ids from an SSE stream until `count` events arrived, then disconnects. */
async function readIds(stream: ReadableStream<Uint8Array>, count: number, abort: AbortController) {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  const ids: number[] = [];
  const deadline = Date.now() + 10_000;
  while (ids.length < count) {
    if (Date.now() > deadline) throw new Error(`only ${ids.length} of ${count} events arrived`);
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let end = buffer.indexOf("\n\n");
    while (end >= 0) {
      const frame = buffer.slice(0, end);
      buffer = buffer.slice(end + 2);
      const id = /^id: (\d+)$/m.exec(frame)?.[1];
      if (id) ids.push(Number(id));
      end = buffer.indexOf("\n\n");
    }
  }
  abort.abort();
  await reader.cancel().catch(() => undefined);
  return ids;
}

function open(specimenId: string, afterId: number) {
  const abort = new AbortController();
  const stream = specimenEventStream({
    db: database().db,
    listener,
    specimenId,
    afterId,
    signal: abort.signal,
    heartbeatMs: 1000,
  });
  return { stream, abort };
}

describe("specimen event stream", () => {
  it("resumes after any disconnect point with exactly the later events", async () => {
    await fc.assert(
      fc.asyncProperty(fc.integer({ min: 1, max: 12 }), fc.nat(), async (total, cut) => {
        const specimen = await newSpecimen();
        const ids: number[] = [];
        for (let i = 0; i < total; i += 1) ids.push((await append(specimen.id)).id);
        const seen = cut % (total + 1);
        const lastSeen = seen === 0 ? 0 : (ids[seen - 1] as number);
        const { stream, abort } = open(specimen.id, lastSeen);
        expect(await readIds(stream, total - seen, abort)).toEqual(ids.slice(seen));
      }),
      { numRuns: 15 },
    );
  });

  it("delivers events committed after connecting, in order, and only for its specimen", async () => {
    const specimen = await newSpecimen();
    const other = await newSpecimen();
    const before = await append(specimen.id);
    const { stream, abort } = open(specimen.id, before.id);
    const reading = readIds(stream, 3, abort);
    await new Promise((r) => setTimeout(r, 200));
    const later: number[] = [];
    for (let i = 0; i < 3; i += 1) {
      await append(other.id);
      later.push((await append(specimen.id)).id);
    }
    expect(await reading).toEqual(later);
  });

  it("reads the resume point from Last-Event-ID", () => {
    const at = (headers: Record<string, string>, url = "http://x/api") =>
      resumeId(new Request(url, { headers }));
    expect(at({ "last-event-id": "42" })).toBe(42);
    expect(at({}, "http://x/api?after=7")).toBe(7);
    expect(at({ "last-event-id": "-1" })).toBe(0);
    expect(at({ "last-event-id": "1e9" })).toBe(0);
    expect(at({})).toBe(0);
  });
});
