import { Button } from "@orrery/ui";
import { Link, useNavigate } from "@tanstack/react-router";
import { type ReactNode, useState } from "react";
import { authClient } from "../lib/auth-client.ts";
import { NotificationTray } from "./notification-tray.tsx";

/** Signed-in frame: wordmark, the two places a user goes, notices, and sign-out, over the desk. */
export function AppShell(props: {
  userName: string;
  isAdmin: boolean;
  unreadNotices: number;
  children: ReactNode;
}) {
  const navigate = useNavigate();
  const [signingOut, setSigningOut] = useState(false);
  const [failed, setFailed] = useState(false);

  async function signOut() {
    setSigningOut(true);
    const { error } = await authClient.signOut();
    setSigningOut(false);
    if (error) {
      setFailed(true);
      return;
    }
    await navigate({ to: "/sign-in" });
  }

  const nav =
    "font-display-sc text-parchment tracking-[0.14em] hover:text-bone data-[status=active]:text-bone data-[status=active]:underline data-[status=active]:decoration-brass data-[status=active]:underline-offset-8";

  return (
    <div className="desk flex min-h-dvh flex-col text-bone">
      <header className="flex flex-wrap items-center gap-x-10 gap-y-3 border-umber border-b px-6 py-4 sm:px-10">
        <Link
          to="/cabinet"
          className="font-display-sc text-bone text-xl tracking-[0.32em] hover:text-brass-bright"
        >
          Orrery
        </Link>
        <nav aria-label="Main" className="flex gap-8">
          <Link to="/cabinet" className={nav}>
            Cabinet
          </Link>
          <Link to="/account" className={nav}>
            Account
          </Link>
          {props.isAdmin ? (
            <Link to="/admin" className={nav}>
              Operator
            </Link>
          ) : null}
        </nav>
        <div className="ml-auto flex items-center gap-6">
          <NotificationTray unread={props.unreadNotices} />
          <span className="hidden font-display text-parchment italic sm:inline">
            {props.userName}
          </span>
          <Button variant="quiet" onPress={signOut} isPending={signingOut}>
            Sign out
          </Button>
        </div>
        {failed ? (
          <p role="alert" className="w-full text-right font-display text-brass-bright italic">
            Signing out failed. Check your connection and try again.
          </p>
        ) : null}
      </header>
      {props.children}
    </div>
  );
}
