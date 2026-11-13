import { createFileRoute } from "@tanstack/react-router";
import { sql } from "drizzle-orm";
import { database, databaseReady } from "../../server/db.ts";
import { storage } from "../../server/storage.ts";

/** Liveness and dependency status for Compose, Kamal, and Gatus (requirement 11.4). */
export const Route = createFileRoute("/api/health")({
  server: {
    handlers: {
      GET: async () => {
        const checks: Record<string, "ok" | "unreachable" | "migrations pending"> = {};
        try {
          await database().db.execute(sql`select 1`);
          await databaseReady();
          checks.database = "ok";
        } catch (error) {
          checks.database =
            error instanceof Error && error.name === "MigrationsPendingError"
              ? "migrations pending"
              : "unreachable";
        }
        checks.storage = (await storage().reachable()) ? "ok" : "unreachable";
        // The object store being down degrades uploads and playback, not the site: still 200.
        const ok = checks.database === "ok";
        const allOk = Object.values(checks).every((v) => v === "ok");
        return Response.json(
          { status: allOk ? "ok" : "degraded", checks },
          { status: ok ? 200 : 503, headers: { "cache-control": "no-store" } },
        );
      },
    },
  },
});
