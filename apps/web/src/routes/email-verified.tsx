import { Banner } from "@orrery/ui";
import { createFileRoute, Link } from "@tanstack/react-router";
import { z } from "zod";
import { AuthFrame } from "../components/auth-frame.tsx";
import { getSession } from "../server/session.ts";

/** Better Auth redirects here after a confirmation link is opened, with `error` on failure. */
export const Route = createFileRoute("/email-verified")({
  head: () => ({ meta: [{ title: "Email confirmation · Orrery" }] }),
  validateSearch: z.object({ error: z.string().max(100).optional() }),
  loader: () => getSession(),
  component: EmailVerified,
});

function EmailVerified() {
  const { error } = Route.useSearch();
  const session = Route.useLoaderData();

  if (error) {
    return (
      <AuthFrame plate={3} title="That link did not work">
        <div className="flex flex-col gap-5">
          <Banner tone="error" title="The confirmation link is invalid or has expired." />
          <p className="text-lampblack">
            Sign in with your email and password and we will send a fresh link automatically.
          </p>
          <Link to="/sign-in" className="o-link">
            Go to sign in
          </Link>
        </div>
      </AuthFrame>
    );
  }

  return (
    <AuthFrame plate={3} title="Email confirmed" caption="The register is open.">
      <div className="flex flex-col gap-5">
        <Banner tone="success" title="Your email address is confirmed." />
        {session ? (
          <Link to="/cabinet" className="o-link">
            Continue to your cabinet
          </Link>
        ) : (
          <Link to="/sign-in" className="o-link">
            Sign in to continue
          </Link>
        )}
      </div>
    </AuthFrame>
  );
}
