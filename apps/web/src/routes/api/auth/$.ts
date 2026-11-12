import { createFileRoute } from "@tanstack/react-router";
import { auth } from "../../../server/auth.ts";
import { databaseReady } from "../../../server/db.ts";

async function handle({ request }: { request: Request }) {
  await databaseReady();
  return auth().handler(request);
}

export const Route = createFileRoute("/api/auth/$")({
  server: { handlers: { GET: handle, POST: handle } },
});
