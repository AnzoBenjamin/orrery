import { passkey } from "@better-auth/passkey";
import type { BetterAuthOptions } from "better-auth";

/**
 * The Better Auth options that determine its database tables. The web app's runtime config
 * (apps/web/src/server/auth.ts) spreads these, and `pnpm --filter @orrery/db auth:generate`
 * regenerates src/schema/auth.ts from them, so the schema and the runtime cannot drift apart.
 */
export const authSchemaOptions = {
  plugins: [passkey()],
  rateLimit: { enabled: true, storage: "database" },
  user: {
    additionalFields: {
      /** "admin" unlocks the operator pages. Never settable through sign-up or profile updates. */
      role: { type: "string", required: true, defaultValue: "user", input: false },
    },
  },
  advanced: {
    database: { generateId: "uuid" },
  },
} satisfies Partial<BetterAuthOptions>;
