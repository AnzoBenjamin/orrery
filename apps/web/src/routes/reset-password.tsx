import { Banner, Form, SubmitButton, TextField } from "@orrery/ui";
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { z } from "zod";
import { AuthFrame } from "../components/auth-frame.tsx";
import { authClient, authErrorMessage } from "../lib/auth-client.ts";

/** Better Auth redirects reset links here with `token`, or with `error=INVALID_TOKEN`. */
export const Route = createFileRoute("/reset-password")({
  head: () => ({ meta: [{ title: "Choose a new password · Orrery" }] }),
  validateSearch: z.object({
    token: z.string().min(1).max(500).optional(),
    error: z.string().max(100).optional(),
  }),
  component: ResetPassword,
});

function ResetPassword() {
  const { token, error: linkError } = Route.useSearch();
  const navigate = useNavigate();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!token || linkError) {
    return (
      <AuthFrame plate={4} title="That link did not work">
        <div className="flex flex-col gap-5">
          <Banner tone="error" title="This reset link is invalid, already used, or expired." />
          <Link to="/forgot-password" className="text-brass-bright underline underline-offset-4">
            Request a new link
          </Link>
        </div>
      </AuthFrame>
    );
  }

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const newPassword = String(form.get("password"));
    if (newPassword !== String(form.get("confirm"))) {
      setError("The two passwords do not match. Type the same password in both fields.");
      return;
    }
    setPending(true);
    setError(null);
    const { error: failure } = await authClient.resetPassword({ newPassword, token: token ?? "" });
    setPending(false);
    if (failure) {
      setError(authErrorMessage(failure));
      return;
    }
    await navigate({ to: "/sign-in", search: { reset: "1" } });
  }

  return (
    <AuthFrame
      plate={4}
      title="Choose a new password"
      caption="Every other session will be signed out."
    >
      <Form onSubmit={onSubmit} className="flex flex-col gap-5">
        {error ? <Banner tone="error" title={error} /> : null}
        <TextField
          label="New password"
          name="password"
          type="password"
          autoComplete="new-password"
          description="At least 10 characters."
          isRequired
          minLength={10}
          maxLength={128}
        />
        <TextField
          label="Repeat the new password"
          name="confirm"
          type="password"
          autoComplete="new-password"
          isRequired
        />
        <SubmitButton isPending={pending}>Change password</SubmitButton>
      </Form>
    </AuthFrame>
  );
}
