import { createServerFn } from "@tanstack/react-start";
import { call } from "../server/call.ts";
import {
  notificationList,
  notificationMarkAllRead,
  notificationMarkRead,
  notificationUnreadCount,
} from "../server/operations/notifications.ts";
import { typed } from "./typed.ts";

export const listNotificationsFn = createServerFn({ method: "GET" })
  .validator(typed(notificationList.input))
  .handler(({ data }) => call(notificationList, data));

export const unreadNotificationsFn = createServerFn({ method: "GET" })
  .validator(typed(notificationUnreadCount.input))
  .handler(({ data }) => call(notificationUnreadCount, data));

export const markNotificationReadFn = createServerFn({ method: "POST" })
  .validator(typed(notificationMarkRead.input))
  .handler(({ data }) => call(notificationMarkRead, data));

export const markAllNotificationsReadFn = createServerFn({ method: "POST" })
  .validator(typed(notificationMarkAllRead.input))
  .handler(({ data }) => call(notificationMarkAllRead, data));
