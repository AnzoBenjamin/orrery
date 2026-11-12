import { Banner, Button, Plate } from "@orrery/ui";
import { createFileRoute, Link, redirect, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { authClient } from "../lib/auth-client.ts";
import { getSession } from "../server/session.ts";

export const Route = createFileRoute("/account")({
  head: () => ({ meta: [{ title: "Account · Orrery" }] }),
  beforeLoad: async ({ location }) => {
    const session = await getSession();
    if (!session) throw redirect({ to: "/sign-in", search: { redirect: location.href } });
    return { session };
  },
  component: Account,
});

function Account() {
  const { session } = Route.useRouteContext();
  const navigate = useNavigate();
  const [state, setState] = useState<"idle" | "signing-out" | "error">("idle");

  async function signOut() {
    setState("signing-out");
    const { error } = await authClient.signOut();
    if (error) {
      setState("error");
      return;
    }
    await navigate({ to: "/sign-in" });
  }

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="flex items-center justify-between border-umber border-b px-6 py-4 sm:px-10">
        <Link
          to="/"
          className="font-display text-brass text-lg uppercase tracking-[0.2em] hover:text-brass-bright"
        >
          Orrery
        </Link>
        <Button variant="quiet" onPress={signOut} isPending={state === "signing-out"}>
          Sign out
        </Button>
      </header>
      <main id="main" className="mx-auto w-full max-w-2xl px-4 py-10">
        <Plate number={5} title="Account" caption={session.user.name}>
          <div className="flex flex-col gap-5">
            {state === "error" ? (
              <Banner
                tone="error"
                title="Signing out failed. Check your connection and try again."
              />
            ) : null}
            <dl className="grid grid-cols-[max-content_1fr] gap-x-6 gap-y-3">
              <dt className="text-parchment">Name</dt>
              <dd className="text-bone">{session.user.name}</dd>
              <dt className="text-parchment">Email</dt>
              <dd className="font-instrument text-bone">{session.user.email}</dd>
              <dt className="text-parchment">Status</dt>
              <dd className="text-bone">
                {session.user.emailVerified ? "Email confirmed" : "Email not yet confirmed"}
              </dd>
            </dl>
          </div>
        </Plate>
      </main>
    </div>
  );
}
