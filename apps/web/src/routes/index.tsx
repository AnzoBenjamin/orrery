import { createFileRoute, redirect } from "@tanstack/react-router";
import { getSession } from "../server/session.ts";

/**
 * The public landing page (workbench requirement 2) replaces this redirect when the first real
 * specimen has been processed. Until then visitors go straight to sign-in.
 */
export const Route = createFileRoute("/")({
  beforeLoad: async () => {
    const session = await getSession();
    throw redirect({ to: session ? "/cabinet" : "/sign-in" });
  },
});
