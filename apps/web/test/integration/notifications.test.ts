import { createNotification, newId, schema } from "@orrery/db";
import { describe, expect, it } from "vitest";
import { invoke } from "../../src/server/operations/define.ts";
import {
  notificationList,
  notificationMarkAllRead,
  notificationMarkRead,
  notificationUnreadCount,
} from "../../src/server/operations/notifications.ts";
import { userActor, withTestDatabase } from "./support.ts";

const database = withTestDatabase();

const about = () => ({
  specimenId: newId(),
  specimenTitle: "Mantel clock",
  footageId: newId(),
  filename: "clip.mp4",
});

describe("notification operations", () => {
  it("lists newest first with the unread count, and marks one or all read", async () => {
    const user = await userActor(database());
    const ready = await createNotification(database().db, {
      userId: user.userId,
      kind: "footage.ready",
      payload: about(),
    });
    await createNotification(database().db, {
      userId: user.userId,
      kind: "footage.rejected",
      payload: { ...about(), reason: "This clip is 7.0 minutes long; the limit is 5 minutes." },
    });

    const listed = await invoke(database().deps, notificationList, user, {});
    if (!listed.ok) throw new Error(listed.error.message);
    expect(listed.value.unread).toBe(2);
    expect(listed.value.items.map((n) => n.kind)).toEqual(["footage.rejected", "footage.ready"]);

    expect(
      await invoke(database().deps, notificationMarkRead, user, { notificationId: ready.id }),
    ).toEqual({ ok: true, value: { unread: 1 } });
    // Marking it again is harmless.
    expect(
      await invoke(database().deps, notificationMarkRead, user, { notificationId: ready.id }),
    ).toEqual({ ok: true, value: { unread: 1 } });
    expect(await invoke(database().deps, notificationMarkAllRead, user, {})).toEqual({
      ok: true,
      value: { unread: 0 },
    });
    expect(await invoke(database().deps, notificationUnreadCount, user, {})).toEqual({
      ok: true,
      value: { unread: 0 },
    });
    expect(
      await invoke(database().deps, notificationMarkRead, user, { notificationId: newId() }),
    ).toMatchObject({ ok: false, error: { kind: "NotFound" } });
  });

  it("leaves out stored notices it can no longer read", async () => {
    const user = await userActor(database());
    await database()
      .db.insert(schema.notification)
      .values({ userId: user.userId, kind: "retired.kind", payload: { anything: true } });
    const listed = await invoke(database().deps, notificationList, user, {});
    expect(listed).toMatchObject({ ok: true, value: { items: [], unread: 1 } });
  });
});
