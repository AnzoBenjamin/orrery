// Used only by the Better Auth CLI to generate src/schema/auth.ts. It never handles requests.
import { drizzleAdapter } from "@better-auth/drizzle-adapter";
import { betterAuth } from "better-auth";
import { drizzle } from "drizzle-orm/node-postgres";
import { authSchemaOptions } from "./src/auth-options.ts";

// Drizzle's client without a connection: the CLI reads the schema and never queries.
const unconnected = drizzle.mock(); // placeholder-check: allow (Drizzle API name)

export const auth = betterAuth({
  ...authSchemaOptions,
  database: drizzleAdapter(unconnected, { provider: "pg" }),
});
