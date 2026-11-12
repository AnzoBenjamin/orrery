import { createHash } from "node:crypto";
import { drizzleAdapter } from "@better-auth/drizzle-adapter";
import { passkey } from "@better-auth/passkey";
import { schema } from "@orrery/db";
import { authSchemaOptions } from "@orrery/db/auth-options";
import { emailSend, enqueue } from "@orrery/jobs";
import { betterAuth } from "better-auth";
import { tanstackStartCookies } from "better-auth/tanstack-start";
import { database } from "./db.ts";
import { serverEnv } from "./env.ts";
import { jobProducer } from "./jobs.ts";

const HOUR_S = 3600;

/** Tokens can be long JWTs; idempotency keys use their digest instead. */
const digest = (token: string) => createHash("sha256").update(token).digest("hex");

function createAuth() {
  const env = serverEnv();
  const origin = new URL(env.BETTER_AUTH_URL);

  const socialProviders = {
    ...(env.GITHUB_CLIENT_ID && env.GITHUB_CLIENT_SECRET
      ? { github: { clientId: env.GITHUB_CLIENT_ID, clientSecret: env.GITHUB_CLIENT_SECRET } }
      : {}),
    ...(env.GOOGLE_CLIENT_ID && env.GOOGLE_CLIENT_SECRET
      ? { google: { clientId: env.GOOGLE_CLIENT_ID, clientSecret: env.GOOGLE_CLIENT_SECRET } }
      : {}),
  };

  return betterAuth({
    ...authSchemaOptions,
    appName: "Orrery",
    baseURL: env.BETTER_AUTH_URL,
    secret: env.BETTER_AUTH_SECRET,
    trustedOrigins: [origin.origin],
    database: drizzleAdapter(database().db, { provider: "pg", schema }),

    emailAndPassword: {
      enabled: true,
      requireEmailVerification: true,
      minPasswordLength: 10,
      maxPasswordLength: 128,
      resetPasswordTokenExpiresIn: HOUR_S,
      revokeSessionsOnPasswordReset: true,
      sendResetPassword: async ({ user, url, token }) => {
        await enqueue(await jobProducer(), emailSend, {
          message: { template: "reset-password", to: user.email, name: user.name, url },
          idempotencyKey: `reset-password:${digest(token)}`,
        });
      },
    },
    emailVerification: {
      sendOnSignUp: true,
      sendOnSignIn: true,
      autoSignInAfterVerification: true,
      expiresIn: 24 * HOUR_S,
      sendVerificationEmail: async ({ user, url, token }) => {
        await enqueue(await jobProducer(), emailSend, {
          message: { template: "verify-email", to: user.email, name: user.name, url },
          idempotencyKey: `verify-email:${digest(token)}`,
        });
      },
    },
    socialProviders,
    account: { accountLinking: { enabled: true, trustedProviders: ["github", "google"] } },
    session: {
      expiresIn: 30 * 24 * HOUR_S,
      updateAge: 24 * HOUR_S,
    },

    rateLimit: {
      ...authSchemaOptions.rateLimit,
      window: 60,
      max: 100,
      customRules: {
        "/sign-in/email": { window: 60, max: 5 },
        "/sign-up/email": { window: 3600, max: 5 },
        "/request-password-reset": { window: 3600, max: 3 },
        "/send-verification-email": { window: 3600, max: 3 },
      },
    },

    plugins: [
      passkey({ rpID: origin.hostname, rpName: "Orrery", origin: origin.origin }),
      // Must stay last: it writes Set-Cookie headers through TanStack Start.
      tanstackStartCookies(),
    ],
    advanced: {
      ...authSchemaOptions.advanced,
      cookiePrefix: "orrery",
      useSecureCookies: env.NODE_ENV === "production",
      defaultCookieAttributes: { httpOnly: true, sameSite: "lax" },
      ipAddress: { ipAddressHeaders: ["x-forwarded-for"] },
    },
  });
}

let instance: ReturnType<typeof createAuth> | undefined;

export function auth() {
  instance ??= createAuth();
  return instance;
}

export type Session = NonNullable<
  Awaited<ReturnType<ReturnType<typeof auth>["api"]["getSession"]>>
>;
