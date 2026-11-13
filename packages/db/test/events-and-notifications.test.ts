import pg from "pg";
import { describe, expect, it } from "vitest";
import {
  appendDomainEvent,
  claimPendingDeletions,
  countUnreadNotifications,
  createNotification,
  createSpecimen,
  enqueueObjectDeletions,
  getUserPreferences,
  listDomainEventsAfter,
  listNotifications,
  markAllNotificationsRead,
  markDeletionCompleted,
  markNotificationRead,
  newId,
  recordDeletionFailure,
  specimenChannel,
  updateUserPreferences,
} from "../src/index.ts";
import { insertUser, useTestDatabase } from "./support.ts";

const database = useTestDatabase();

describe("domain events", () => {
  it("notifies listeners with the event id once the event is committed", async () => {
    const owner = await insertUser(database());
    const s = await createSpecimen(database().db, { ownerId: owner.id, title: "Orrery" });
    const listener = new pg.Client({ connectionString: database().url });
    await listener.connect();
    try {
      const received = new Promise<string>((resolve) => {
        listener.on("notification", (m) => resolve(m.payload ?? ""));
      });
      await listener.query(`listen "${specimenChannel(s.id)}"`);
      const event = await appendDomainEvent(database().db, {
        specimenId: s.id,
        type: "analysis.progress",
        payload: { stage: "tracking", fraction: 0.4 },
      });
      expect(await received).toBe(String(event.id));
    } finally {
      await listener.end();
    }
  });

  it("replays exactly the events after a given id, in order", async () => {
    const owner = await insertUser(database());
    const s = await createSpecimen(database().db, { ownerId: owner.id, title: "Escapement" });
    const ids: number[] = [];
    for (let i = 0; i < 5; i += 1) {
      ids.push(
        (await appendDomainEvent(database().db, { specimenId: s.id, type: "t", payload: { i } }))
          .id,
      );
    }
    const after = ids[1] as number;
    const replay = await listDomainEventsAfter(database().db, {
      specimenId: s.id,
      afterId: after,
      limit: 100,
    });
    expect(replay.map((e) => e.id)).toEqual(ids.slice(2));
  });
});

describe("notifications", () => {
  it("lists, counts, and marks a user's notifications read", async () => {
    const a = await insertUser(database());
    const b = await insertUser(database());
    const about = {
      specimenId: newId(),
      specimenTitle: "Clock",
      footageId: newId(),
      filename: "clip.mp4",
    };
    const first = await createNotification(database().db, {
      userId: a.id,
      kind: "footage.rejected",
      payload: { ...about, reason: "This file is not a video we can read." },
    });
    await createNotification(database().db, {
      userId: a.id,
      kind: "footage.ready",
      payload: about,
    });
    expect(await countUnreadNotifications(database().db, a.id)).toBe(2);
    expect(await markNotificationRead(database().db, { id: first.id, userId: b.id })).toBe(
      undefined,
    );
    expect(
      (await markNotificationRead(database().db, { id: first.id, userId: a.id }))?.readAt,
    ).toBeInstanceOf(Date);
    expect(await markAllNotificationsRead(database().db, a.id)).toBe(1);
    expect(await countUnreadNotifications(database().db, a.id)).toBe(0);
    expect((await listNotifications(database().db, a.id, { limit: 1 })).nextCursor).toBeDefined();
  });

  it("refuses payloads that do not match their kind", async () => {
    const a = await insertUser(database());
    await expect(
      createNotification(database().db, {
        userId: a.id,
        kind: "footage.ready",
        payload: { specimenId: "not-a-uuid" } as never,
      }),
    ).rejects.toThrow();
  });
});

describe("object deletions", () => {
  it("never hands the same pending deletion to two concurrent workers", async () => {
    await enqueueObjectDeletions(database().db, ["k/1", "k/2", "k/3", "k/4"]);
    const claimed = await Promise.all(
      [0, 1].map(() =>
        database().db.transaction(async (tx) => {
          const rows = await claimPendingDeletions(tx, 2);
          await new Promise((r) => setTimeout(r, 100));
          return rows.map((r) => r.objectKey);
        }),
      ),
    );
    const all = claimed.flat();
    expect(new Set(all).size).toBe(all.length);
    expect(all.length).toBeGreaterThanOrEqual(2);
  });

  it("records failures and completion", async () => {
    const [row] = await enqueueObjectDeletions(database().db, ["k/fail-then-ok"]);
    if (!row) throw new Error("no row");
    expect((await recordDeletionFailure(database().db, row.id, "503 Slow Down"))?.attempts).toBe(1);
    const done = await markDeletionCompleted(database().db, row.id);
    expect(done?.completedAt).toBeInstanceOf(Date);
    expect(done?.lastError).toBeNull();
  });
});

describe("user preferences", () => {
  it("returns defaults until changed, then persists changes", async () => {
    const u = await insertUser(database());
    expect(await getUserPreferences(database().db, u.id)).toEqual({
      userId: u.id,
      analysisCompleteEmail: true,
      soundEnabled: false,
      units: "metric",
    });
    await updateUserPreferences(database().db, u.id, { analysisCompleteEmail: false });
    const updated = await updateUserPreferences(database().db, u.id, { units: "imperial" });
    expect(updated).toMatchObject({ analysisCompleteEmail: false, units: "imperial" });
  });
});
