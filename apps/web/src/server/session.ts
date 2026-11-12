import { createServerFn } from "@tanstack/react-start";
import { getRequestHeaders } from "@tanstack/react-start/server";
import { auth } from "./auth.ts";
import { databaseReady } from "./db.ts";

/** The signed-in user's session, or null. Used by route guards in `beforeLoad`. */
export const getSession = createServerFn({ method: "GET" }).handler(async () => {
  await databaseReady();
  const session = await auth().api.getSession({ headers: getRequestHeaders() });
  if (!session) return null;
  return {
    user: {
      id: session.user.id,
      name: session.user.name,
      email: session.user.email,
      emailVerified: session.user.emailVerified,
    },
    session: { id: session.session.id, expiresAt: session.session.expiresAt.toISOString() },
  };
});

export type SessionInfo = NonNullable<Awaited<ReturnType<typeof getSession>>>;
