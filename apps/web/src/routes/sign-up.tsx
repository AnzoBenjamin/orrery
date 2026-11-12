import { Banner, Form, SubmitButton, TextField } from "@orrery/ui";
import { createFileRoute, Link, redirect, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { AuthFrame } from "../components/auth-frame.tsx";
import { authClient, authErrorMessage } from "../lib/auth-client.ts";
import { getSession } from "../server/session.ts";

export const Route = createFileRoute("/sign-up")({
  head: () => ({ meta: [{ title: "Create an account · Orrery" }] }),
  beforeLoad: async () => {
    if (await getSession()) throw redirect({ to: "/account" });
  },
  component: SignUp,
});

function SignUp() {
  const navigate = useNavigate();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const email = String(form.get("email"));
    setPending(true);
    setError(null);
    const { error: failure } = await authClient.signUp.email({
      name: String(form.get("name")).trim(),
      email,
      password: String(form.get("password")),
      callbackURL: "/email-verified",
    });
    setPending(false);
    if (failure) {
      setError(authErrorMessage(failure));
      return;
    }
    await navigate({ to: "/check-email", search: { email } });
  }

  return (
    <AuthFrame
      plate={1}
      title="Open a register"
      caption="An account for your specimens and footage."
    >
      <Form onSubmit={onSubmit} className="flex flex-col gap-5">
        {error ? <Banner tone="error" title={error} /> : null}
        <TextField label="Name" name="name" autoComplete="name" isRequired maxLength={200} />
        <TextField label="Email" name="email" type="email" autoComplete="email" isRequired />
        <TextField
          label="Password"
          name="password"
          type="password"
          autoComplete="new-password"
          description="At least 10 characters."
          isRequired
          minLength={10}
          maxLength={128}
        />
        <SubmitButton isPending={pending}>Create account</SubmitButton>
      </Form>
      <p className="mt-6 text-parchment text-sm">
        Already registered?{" "}
        <Link to="/sign-in" className="text-brass-bright underline underline-offset-4">
          Sign in
        </Link>
      </p>
    </AuthFrame>
  );
}
