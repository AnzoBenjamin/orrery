import { and, asc, eq, gt, sql } from "drizzle-orm";
import type { Executor } from "../client.ts";
import { type DomainEventBody, domainEventBody } from "../event-kinds.ts";
import { domainEvent } from "../schema/index.ts";

export type DomainEvent = typeof domainEvent.$inferSelect;

/** NOTIFY channel carrying new event ids for one specimen. */
export function specimenChannel(specimenId: string): string {
  return `specimen:${specimenId}`;
}

/**
 * Appends an event and notifies listeners in the same transaction, so a listener woken by the
 * notification always finds the row (NOTIFY is delivered on commit).
 */
export async function appendDomainEvent(
  ex: Executor,
  input: { specimenId: string } & DomainEventBody,
): Promise<DomainEvent> {
  const body = domainEventBody.parse({ type: input.type, payload: input.payload });
  return ex.transaction(async (tx) => {
    const [row] = await tx
      .insert(domainEvent)
      .values({ specimenId: input.specimenId, type: body.type, payload: body.payload })
      .returning();
    if (!row) throw new Error("domain event insert returned no row");
    await tx.execute(
      sql`select pg_notify(${specimenChannel(input.specimenId)}, ${String(row.id)})`,
    );
    return row;
  });
}

/** Events of a specimen with id greater than `afterId`, oldest first (SSE replay). */
export async function listDomainEventsAfter(
  ex: Executor,
  input: { specimenId: string; afterId: number; limit: number },
): Promise<DomainEvent[]> {
  return ex
    .select()
    .from(domainEvent)
    .where(and(eq(domainEvent.specimenId, input.specimenId), gt(domainEvent.id, input.afterId)))
    .orderBy(asc(domainEvent.id))
    .limit(input.limit);
}
