import { defineConfig } from "drizzle-kit";

// Migrations are generated with `pnpm --filter @orrery/db generate`, reviewed, and committed.
// They are applied only through apps/worker/src/migrate.ts (`make migrate`), never with `drizzle-kit push`.
export default defineConfig({
  dialect: "postgresql",
  schema: "./src/schema/index.ts",
  out: "./migrations",
  strict: true,
  verbose: true,
});
