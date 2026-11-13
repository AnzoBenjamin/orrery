import { createFileRoute, Outlet, redirect } from "@tanstack/react-router";
import { AppShell } from "../components/app-shell.tsx";
import { getSession } from "../server/session.ts";

/** Pathless layout for signed-in pages: guards the session and draws the shell. */
export const Route = createFileRoute("/_app")({
  beforeLoad: async ({ location }) => {
    const session = await getSession();
    if (!session) throw redirect({ to: "/sign-in", search: { redirect: location.href } });
    return { session };
  },
  component: AppLayout,
});

function AppLayout() {
  const { session } = Route.useRouteContext();
  return (
    <AppShell userName={session.user.name}>
      <Outlet />
    </AppShell>
  );
}
