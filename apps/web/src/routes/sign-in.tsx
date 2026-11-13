import { Banner, Button, Form, Rule, SubmitButton, TextField } from "@orrery/ui";
import { createFileRoute, Link, redirect, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { z } from "zod";
import { AuthFrame } from "../components/auth-frame.tsx";
import { authClient, authErrorMessage } from "../lib/auth-client.ts";
import { safeRedirect } from "../lib/safe-redirect.ts";
import { getAuthMethods } from "../server/auth-methods.ts";
import { getSession } from "../server/session.ts";

const search = z.object({
  redirect: z.string().max(2000).optional(),
  reset: z.literal("1").optional(),
  deleted: z.literal("1").optional(),
});

export const Route = createFileRoute("/sign-in")({
  head: () => ({ meta: [{ title: "Sign in · Orrery" }] }),
  validateSearch: search,
  beforeLoad: async ({ search: s }) => {
    if (await getSession()) throw redirect({ href: safeRedirect(s.redirect, "/cabinet") });
  },
  loader: () => getAuthMethods(),
  component: SignIn,
});

function SignIn() {
  const methods = Route.useLoaderData();
  const { redirect: target, reset, deleted } = Route.useSearch();
  const destination = safeRedirect(target, "/cabinet");
  const navigate = useNavigate();
  const [pending, setPending] = useState<"password" | "passkey" | "github" | "google" | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function finish() {
    await navigate({ href: destination });
  }

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setPending("password");
    setError(null);
    const { error: failure } = await authClient.signIn.email({
      email: String(form.get("email")),
      password: String(form.get("password")),
    });
    setPending(null);
    if (failure) {
      setError(authErrorMessage(failure));
      return;
    }
    await finish();
  }

  async function withPasskey() {
    setPending("passkey");
    setError(null);
    const result = await authClient.signIn.passkey();
    setPending(null);
    if (result?.error) {
      setError(
        "No passkey on this device matched an account, or the request was cancelled. Use your email and password instead.",
      );
      return;
    }
    await finish();
  }

  async function withProvider(provider: "github" | "google") {
    setPending(provider);
    setError(null);
    const { error: failure } = await authClient.signIn.social({
      provider,
      callbackURL: destination,
      errorCallbackURL: "/sign-in",
    });
    if (failure) {
      setPending(null);
      setError(authErrorMessage(failure));
    }
  }

  return (
    <AuthFrame plate={2} title="Sign in" caption="Return to the workshop.">
      <div className="flex flex-col gap-5">
        {reset ? (
          <Banner tone="success" title="Password changed. Sign in with the new one." />
        ) : null}
        {deleted ? (
          <Banner tone="success" title="Your account and everything in it have been deleted." />
        ) : null}
        {error ? <Banner tone="error" title={error} /> : null}
        <Form onSubmit={onSubmit} className="flex flex-col gap-5">
          <TextField
            label="Email"
            name="email"
            type="email"
            autoComplete="email webauthn"
            isRequired
          />
          <TextField
            label="Password"
            name="password"
            type="password"
            autoComplete="current-password"
            isRequired
          />
          <div className="flex items-center justify-between gap-4">
            <SubmitButton
              isPending={pending === "password"}
              isDisabled={pending !== null && pending !== "password"}
            >
              Sign in
            </SubmitButton>
            <Link to="/forgot-password" className="o-link text-sm">
              Forgot your password?
            </Link>
          </div>
        </Form>
        <Rule label="or" />
        <div className="flex flex-col gap-3">
          <Button
            variant="secondary"
            onPress={withPasskey}
            isPending={pending === "passkey"}
            isDisabled={pending !== null && pending !== "passkey"}
          >
            Sign in with a passkey
          </Button>
          {methods.github ? (
            <Button
              variant="secondary"
              onPress={() => withProvider("github")}
              isPending={pending === "github"}
              isDisabled={pending !== null && pending !== "github"}
            >
              Continue with GitHub
            </Button>
          ) : null}
          {methods.google ? (
            <Button
              variant="secondary"
              onPress={() => withProvider("google")}
              isPending={pending === "google"}
              isDisabled={pending !== null && pending !== "google"}
            >
              Continue with Google
            </Button>
          ) : null}
        </div>
      </div>
      <p className="mt-6 text-umber text-sm">
        New here?{" "}
        <Link to="/sign-up" className="o-link">
          Create an account
        </Link>
      </p>
    </AuthFrame>
  );
}
