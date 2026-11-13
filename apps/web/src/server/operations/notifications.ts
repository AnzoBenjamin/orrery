import {
  countUnreadNotifications,
  findNotification,
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
  type NotificationBody,
  notificationBody,
} from "@orrery/db";
import { z } from "zod";
import { notFound } from "../domain-errors.ts";
import { requireUser } from "../policy.ts";
import { defineOperation } from "./define.ts";

export type NotificationView = NotificationBody & {
  id: string;
  createdAt: string;
  read: boolean;
};

export const notificationList = defineOperation({
  name: "notification.list",
  input: z.object({
    limit: z.number().int().min(1).max(50).default(20),
    before: z.uuid().optional(),
  }),
  run: async ({ actor, input, tx }) => {
    const user = requireUser(actor);
    const page = await listNotifications(tx, user.userId, input);
    const items: NotificationView[] = [];
    for (const row of page.items) {
      // Rows from an older release that no longer parse are left out rather than misrendered.
      const body = notificationBody.safeParse({ kind: row.kind, payload: row.payload });
      if (body.success) {
        items.push({
          ...body.data,
          id: row.id,
          createdAt: row.createdAt.toISOString(),
          read: row.readAt !== null,
        });
      }
    }
    return {
      items,
      nextCursor: page.nextCursor,
      unread: await countUnreadNotifications(tx, user.userId),
    };
  },
});

export const notificationUnreadCount = defineOperation({
  name: "notification.unread-count",
  input: z.object({}),
  run: async ({ actor, tx }) => ({
    unread: await countUnreadNotifications(tx, requireUser(actor).userId),
  }),
});

export const notificationMarkRead = defineOperation({
  name: "notification.mark-read",
  input: z.object({ notificationId: z.uuid("That notice does not exist.") }),
  run: async ({ actor, input, tx }) => {
    const user = requireUser(actor);
    const row = await markNotificationRead(tx, { id: input.notificationId, userId: user.userId });
    // Already read is fine; someone else's notice is indistinguishable from a missing one.
    if (!row && !(await findNotification(tx, { id: input.notificationId, userId: user.userId }))) {
      throw notFound("That notice");
    }
    return { unread: await countUnreadNotifications(tx, user.userId) };
  },
});

export const notificationMarkAllRead = defineOperation({
  name: "notification.mark-all-read",
  input: z.object({}),
  run: async ({ actor, tx }) => {
    const user = requireUser(actor);
    await markAllNotificationsRead(tx, user.userId);
    return { unread: 0 };
  },
});
