// Used only by the Better Auth CLI to generate src/schema/auth.ts. It never handles requests.
import { drizzleAdapter } from "@better-auth/drizzle-adapter";
import { betterAuth } from "better-auth";
import { drizzle } from "drizzle-orm/node-postgres";
import { authSchemaOptions } from "./src/auth-options.ts";

export const auth = betterAuth({
  ...authSchemaOptions,
  database: drizzleAdapter(drizzle.mock(), { provider: "pg" }),
});
