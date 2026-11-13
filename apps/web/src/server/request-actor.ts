import { getRequestHeaders } from "@tanstack/react-start/server";
import { type Actor, anonymous } from "./actor.ts";
import { auth } from "./auth.ts";

/** Resolves the caller of the current request from its session cookie. */
export async function requestActor(): Promise<Actor> {
  const session = await auth().api.getSession({ headers: getRequestHeaders() });
  if (!session) return anonymous;
  return {
    kind: "user",
    userId: session.user.id,
    emailVerified: session.user.emailVerified,
    isAdmin: (session.user as { role?: string }).role === "admin",
  };
}
