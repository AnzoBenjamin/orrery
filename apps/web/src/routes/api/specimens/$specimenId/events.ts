import { createFileRoute } from "@tanstack/react-router";
import { call } from "../../../../server/call.ts";
import { database, databaseListener } from "../../../../server/db.ts";
import { specimenEventsOpen } from "../../../../server/operations/specimens.ts";
import { resumeId, specimenEventStream } from "../../../../server/specimen-events.ts";

/**
 * Live events for one specimen over Server-Sent Events (requirement 8). Authorized through the
 * `specimen.events.open` operation, so it answers 404 to anyone who cannot read the specimen.
 */
export const Route = createFileRoute("/api/specimens/$specimenId/events")({
  server: {
    handlers: {
      GET: async ({ request, params }) => {
        const access = await call(specimenEventsOpen, { specimenId: params.specimenId });
        if (!access.ok) {
          const status =
            access.error.kind === "NotFound" || access.error.kind === "Invalid"
              ? 404
              : access.error.kind === "Unauthenticated"
                ? 401
                : 503;
          return Response.json({ error: access.error.message }, { status });
        }
        const stream = specimenEventStream({
          db: database().db,
          listener: databaseListener(),
          specimenId: access.value.specimenId,
          afterId: resumeId(request),
          signal: request.signal,
        });
        return new Response(stream, {
          headers: {
            "content-type": "text/event-stream; charset=utf-8",
            "cache-control": "no-store",
            connection: "keep-alive",
            // kamal-proxy and nginx-style proxies must not buffer the stream.
            "x-accel-buffering": "no",
          },
        });
      },
    },
  },
});
