import { Banner, Button } from "@orrery/ui";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useState } from "react";
import { z } from "zod";
import { AuthFrame } from "../components/auth-frame.tsx";
import { authClient, authErrorMessage } from "../lib/auth-client.ts";

export const Route = createFileRoute("/check-email")({
  head: () => ({ meta: [{ title: "Confirm your email · Orrery" }] }),
  validateSearch: z.object({ email: z.email() }),
  component: CheckEmail,
});

function CheckEmail() {
  const { email } = Route.useSearch();
  const [state, setState] = useState<"idle" | "sending" | "sent" | { error: string }>("idle");

  async function resend() {
    setState("sending");
    const { error } = await authClient.sendVerificationEmail({
      email,
      callbackURL: "/email-verified",
    });
    setState(error ? { error: authErrorMessage(error) } : "sent");
  }

  return (
    <AuthFrame plate={3} title="Confirm your email" caption="One step before the workshop opens.">
      <div className="flex flex-col gap-5">
        <p className="text-lampblack">
          We sent a confirmation link to <span className="font-instrument">{email}</span>. Open it
          on this device to activate your account. The link expires in 24 hours.
        </p>
        <p className="text-umber text-sm">
          Nothing arrived after a few minutes? Check your spam folder, then send another link.
        </p>
        {state === "sent" ? <Banner tone="success" title="A new link is on its way." /> : null}
        {typeof state === "object" ? <Banner tone="error" title={state.error} /> : null}
        <div className="flex items-center justify-between gap-4">
          <Button variant="secondary" onPress={resend} isPending={state === "sending"}>
            Send another link
          </Button>
          <Link to="/sign-in" className="o-link text-sm">
            Back to sign in
          </Link>
        </div>
      </div>
    </AuthFrame>
  );
}
