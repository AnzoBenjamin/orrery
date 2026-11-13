import { and, desc, eq, isNull, lt, sql } from "drizzle-orm";
import type { Executor } from "../client.ts";
import { type NotificationBody, notificationBody } from "../notification-kinds.ts";
import { notification } from "../schema/index.ts";
import { clampLimit, type Page, type PageRequest, toPage } from "./page.ts";

export type Notification = typeof notification.$inferSelect;

export async function createNotification(
  ex: Executor,
  input: { userId: string } & NotificationBody,
): Promise<Notification> {
  const body = notificationBody.parse({ kind: input.kind, payload: input.payload });
  const [row] = await ex
    .insert(notification)
    .values({ userId: input.userId, kind: body.kind, payload: body.payload })
    .returning();
  if (!row) throw new Error("notification insert returned no row");
  return row;
}

export async function listNotifications(
  ex: Executor,
  userId: string,
  page: PageRequest,
): Promise<Page<Notification>> {
  const limit = clampLimit(page.limit);
  const rows = await ex
    .select()
    .from(notification)
    .where(
      and(
        eq(notification.userId, userId),
        page.before ? lt(notification.id, page.before) : undefined,
      ),
    )
    .orderBy(desc(notification.id))
    .limit(limit + 1);
  return toPage(rows, limit);
}

export async function findNotification(
  ex: Executor,
  input: { id: string; userId: string },
): Promise<Notification | undefined> {
  const [row] = await ex
    .select()
    .from(notification)
    .where(and(eq(notification.id, input.id), eq(notification.userId, input.userId)));
  return row;
}

export async function countUnreadNotifications(ex: Executor, userId: string): Promise<number> {
  const [row] = await ex
    .select({ n: sql<number>`count(*)::int` })
    .from(notification)
    .where(and(eq(notification.userId, userId), isNull(notification.readAt)));
  return row?.n ?? 0;
}

export async function markNotificationRead(
  ex: Executor,
  input: { id: string; userId: string },
): Promise<Notification | undefined> {
  const [row] = await ex
    .update(notification)
    .set({ readAt: sql`now()` })
    .where(
      and(
        eq(notification.id, input.id),
        eq(notification.userId, input.userId),
        isNull(notification.readAt),
      ),
    )
    .returning();
  return row;
}

export async function markAllNotificationsRead(ex: Executor, userId: string): Promise<number> {
  const rows = await ex
    .update(notification)
    .set({ readAt: sql`now()` })
    .where(and(eq(notification.userId, userId), isNull(notification.readAt)))
    .returning({ id: notification.id });
  return rows.length;
}
