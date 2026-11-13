import { Banner, Button } from "@orrery/ui";
import { Link, useRouter } from "@tanstack/react-router";
import { useState } from "react";
import { Dialog, DialogTrigger, Heading, Popover } from "react-aria-components";
import {
  listNotificationsFn,
  markAllNotificationsReadFn,
  markNotificationReadFn,
} from "../functions/notifications.ts";
import { failureMessage } from "../lib/result.ts";
import type { NotificationView } from "../server/operations/notifications.ts";

const timeFormat = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
  timeZone: "UTC",
  timeZoneName: "short",
});

function describe(n: NotificationView): { title: string; detail: string } {
  switch (n.kind) {
    case "footage.ready":
      return {
        title: `${n.payload.filename} is ready`,
        detail: `Checked and stored with ${n.payload.specimenTitle}.`,
      };
    case "footage.rejected":
      return { title: `${n.payload.filename} was rejected`, detail: n.payload.reason };
  }
}

/**
 * The signed-in user's notices (requirement 7.3): finished and failed work, newest first. The
 * count refreshes whenever the page's data does.
 */
export function NotificationTray(props: { unread: number }) {
  const router = useRouter();
  const [items, setItems] = useState<NotificationView[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [unread, setUnread] = useState(props.unread);
  const [shownFor, setShownFor] = useState(props.unread);
  if (props.unread !== shownFor) {
    setShownFor(props.unread);
    setUnread(props.unread);
  }

  async function load() {
    setError(null);
    const result = await listNotificationsFn({ data: { limit: 20 } });
    if (!result.ok) {
      setError(failureMessage(result));
      return;
    }
    setItems(result.value.items);
    setUnread(result.value.unread);
  }

  async function markRead(id: string) {
    const result = await markNotificationReadFn({ data: { notificationId: id } });
    if (result.ok) {
      setUnread(result.value.unread);
      setItems((list) => list?.map((n) => (n.id === id ? { ...n, read: true } : n)) ?? null);
    }
  }

  async function markAll() {
    const result = await markAllNotificationsReadFn({ data: {} });
    if (!result.ok) {
      setError(failureMessage(result));
      return;
    }
    setUnread(0);
    setItems((list) => list?.map((n) => ({ ...n, read: true })) ?? null);
    await router.invalidate();
  }

  const label = unread > 0 ? `Notices, ${unread} unread` : "Notices";

  return (
    <DialogTrigger onOpenChange={(open) => (open ? void load() : undefined)}>
      <Button variant="quiet" aria-label={label}>
        Notices
        {unread > 0 ? (
          <span
            aria-hidden="true"
            className="ml-1.5 inline-flex min-w-5 items-center justify-center bg-brass px-1 font-instrument text-lampblack text-xs not-italic"
          >
            {unread}
          </span>
        ) : null}
      </Button>
      <Popover
        placement="bottom end"
        offset={10}
        className="paper w-[min(26rem,calc(100vw-2rem))] p-2"
      >
        <Dialog aria-label="Notices" className="outline-none">
          {({ close }) => (
            <div className="border border-lampblack/40 px-5 pt-4 pb-5">
              <div className="flex items-baseline justify-between gap-4">
                <Heading slot="title" className="font-display text-2xl text-lampblack">
                  Notices
                </Heading>
                {unread > 0 ? (
                  <Button variant="quiet" onPress={markAll}>
                    Mark all read
                  </Button>
                ) : null}
              </div>
              <div className="mt-3">
                {error ? (
                  <Banner tone="error" title={error} />
                ) : items === null ? (
                  <p className="text-umber" aria-busy="true">
                    Loading notices…
                  </p>
                ) : items.length === 0 ? (
                  <p className="text-umber">
                    Nothing yet. You are told here when footage is checked or work fails.
                  </p>
                ) : (
                  <ul aria-label="Recent notices" className="max-h-96 overflow-y-auto">
                    {items.map((n) => {
                      const { title, detail } = describe(n);
                      return (
                        <li
                          key={n.id}
                          className="border-lampblack/20 border-b py-3 last:border-b-0"
                        >
                          <Link
                            to="/specimens/$specimenId"
                            params={{ specimenId: n.payload.specimenId }}
                            onClick={() => {
                              if (!n.read) void markRead(n.id);
                              close();
                            }}
                            className="block hover:underline hover:decoration-oxblood"
                          >
                            <span className="flex items-baseline gap-2">
                              {n.read ? null : (
                                <span aria-hidden="true" className="size-2 shrink-0 bg-oxblood" />
                              )}
                              <span
                                className={`break-all font-display text-lampblack ${n.read ? "" : "font-semibold"}`}
                              >
                                {n.read ? "" : <span className="sr-only">Unread: </span>}
                                {title}
                              </span>
                            </span>
                            <span className="mt-1 block text-sm text-umber">{detail}</span>
                            <span className="mt-1 block font-instrument text-umber text-xs">
                              {timeFormat.format(new Date(n.createdAt))}
                            </span>
                          </Link>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </div>
            </div>
          )}
        </Dialog>
      </Popover>
    </DialogTrigger>
  );
}
