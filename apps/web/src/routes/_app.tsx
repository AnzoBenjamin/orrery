import { createFileRoute, Outlet, redirect } from "@tanstack/react-router";
import { AppShell } from "../components/app-shell.tsx";
import { unreadNotificationsFn } from "../functions/notifications.ts";
import { getSession } from "../server/session.ts";

/** Pathless layout for signed-in pages: guards the session and draws the shell. */
export const Route = createFileRoute("/_app")({
  beforeLoad: async ({ location }) => {
    const session = await getSession();
    if (!session) throw redirect({ to: "/sign-in", search: { redirect: location.href } });
    return { session };
  },
  // Re-runs whenever page data is refreshed, so the unread count stays current.
  loader: async () => {
    const result = await unreadNotificationsFn({ data: {} });
    return { unreadNotices: result.ok ? result.value.unread : 0 };
  },
  component: AppLayout,
});

function AppLayout() {
  const { session } = Route.useRouteContext();
  const { unreadNotices } = Route.useLoaderData();
  return (
    <AppShell userName={session.user.name} unreadNotices={unreadNotices}>
      <Outlet />
    </AppShell>
  );
}
