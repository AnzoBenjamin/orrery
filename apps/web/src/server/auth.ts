import { createHash } from "node:crypto";
import { drizzleAdapter } from "@better-auth/drizzle-adapter";
import { passkey } from "@better-auth/passkey";
import { deleteSpecimensForOwner, schema } from "@orrery/db";
import { authSchemaOptions } from "@orrery/db/auth-options";
import { emailSend, enqueue } from "@orrery/jobs";
import { betterAuth } from "better-auth";
import { APIError, createAuthMiddleware } from "better-auth/api";
import { tanstackStartCookies } from "better-auth/tanstack-start";
import { ACCOUNT_RATE_LIMITED, checkAccountLimit } from "./account-limits.ts";
import { appLimits } from "./app-limits.ts";
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
    user: {
      ...authSchemaOptions.user,
      deleteUser: {
        enabled: true,
        // The user row's cascade removes specimens and footage rows but would strand their
        // objects in storage, so the specimens are deleted first and their objects queued
        // (requirement 4.8). If the user row then fails to delete, the account is left empty
        // and the request can be retried.
        beforeDelete: async (user) => {
          await deleteSpecimensForOwner(database().db, user.id);
        },
      },
    },
    session: {
      expiresIn: 30 * 24 * HOUR_S,
      updateAge: 24 * HOUR_S,
    },

    rateLimit: {
      ...authSchemaOptions.rateLimit,
      window: 60,
      max: 100 * env.AUTH_RATE_LIMIT_SCALE,
      customRules: {
        "/sign-in/email": { window: 60, max: 5 * env.AUTH_RATE_LIMIT_SCALE },
        "/sign-up/email": { window: 3600, max: 5 * env.AUTH_RATE_LIMIT_SCALE },
        "/request-password-reset": { window: 3600, max: 3 * env.AUTH_RATE_LIMIT_SCALE },
        "/send-verification-email": { window: 3600, max: 3 * env.AUTH_RATE_LIMIT_SCALE },
      },
    },

    hooks: {
      // Per-account limits (requirement 4.4). Better Auth's rateLimit above counts per IP.
      before: createAuthMiddleware(async (ctx) => {
        const refused = await checkAccountLimit(appLimits, ctx.path, ctx.body);
        if (refused) {
          throw new APIError("TOO_MANY_REQUESTS", { message: refused, code: ACCOUNT_RATE_LIMITED });
        }
      }),
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
