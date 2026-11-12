import { Banner, Form, SubmitButton, TextField } from "@orrery/ui";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useState } from "react";
import { AuthFrame } from "../components/auth-frame.tsx";
import { authClient, authErrorMessage } from "../lib/auth-client.ts";

export const Route = createFileRoute("/forgot-password")({
  head: () => ({ meta: [{ title: "Reset your password · Orrery" }] }),
  component: ForgotPassword,
});

function ForgotPassword() {
  const [state, setState] = useState<"idle" | "sending" | "sent" | { error: string }>("idle");

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const email = String(new FormData(event.currentTarget).get("email"));
    setState("sending");
    const { error } = await authClient.requestPasswordReset({
      email,
      redirectTo: "/reset-password",
    });
    setState(error ? { error: authErrorMessage(error) } : "sent");
  }

  return (
    <AuthFrame plate={4} title="Reset your password">
      {state === "sent" ? (
        <div className="flex flex-col gap-5">
          {/* The same message whether or not the address has an account, so it reveals nothing. */}
          <Banner tone="success" title="Check your email.">
            If an account uses that address, a reset link is on its way. It expires in 60 minutes.
          </Banner>
          <Link to="/sign-in" className="text-brass-bright underline underline-offset-4">
            Back to sign in
          </Link>
        </div>
      ) : (
        <Form onSubmit={onSubmit} className="flex flex-col gap-5">
          {typeof state === "object" ? <Banner tone="error" title={state.error} /> : null}
          <p className="text-bone">
            Enter your account's email and we will send a link to choose a new password.
          </p>
          <TextField label="Email" name="email" type="email" autoComplete="email" isRequired />
          <div className="flex items-center justify-between gap-4">
            <SubmitButton isPending={state === "sending"}>Send reset link</SubmitButton>
            <Link to="/sign-in" className="text-brass-bright text-sm underline underline-offset-4">
              Back to sign in
            </Link>
          </div>
        </Form>
      )}
    </AuthFrame>
  );
}
