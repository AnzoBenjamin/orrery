import {
  appendDomainEvent,
  createSpecimen,
  deleteSpecimen,
  listSpecimensForOwner,
  type Specimen,
  updateSpecimen,
} from "@orrery/db";
import { z } from "zod";
import { requireSpecimen, requireUser } from "../policy.ts";
import { defineOperation } from "./define.ts";

const title = z
  .string()
  .trim()
  .min(1, "Give the specimen a name.")
  .max(200, "Keep the name under 200 characters.");
const description = z.string().trim().max(5000, "Keep the description under 5,000 characters.");
const specimenId = z.uuid("That specimen does not exist.");

/** What the UI sees of a specimen. Dates travel as ISO strings. */
export interface SpecimenView {
  id: string;
  title: string;
  description: string;
  createdAt: string;
  updatedAt: string;
  isOwner: boolean;
}

function view(s: Specimen, viewerId: string | null): SpecimenView {
  return {
    id: s.id,
    title: s.title,
    description: s.description,
    createdAt: s.createdAt.toISOString(),
    updatedAt: s.updatedAt.toISOString(),
    isOwner: s.ownerId === viewerId,
  };
}

export const specimenCreate = defineOperation({
  name: "specimen.create",
  input: z.object({ title, description: description.optional() }),
  run: async ({ actor, input, tx }) => {
    const user = requireUser(actor);
    const s = await createSpecimen(tx, {
      ownerId: user.userId,
      title: input.title,
      description: input.description,
    });
    return view(s, user.userId);
  },
});

export const specimenList = defineOperation({
  name: "specimen.list",
  input: z.object({
    limit: z.number().int().min(1).max(100).default(48),
    before: z.uuid().optional(),
  }),
  run: async ({ actor, input, tx }) => {
    const user = requireUser(actor);
    const page = await listSpecimensForOwner(tx, user.userId, input);
    return { items: page.items.map((s) => view(s, user.userId)), nextCursor: page.nextCursor };
  },
});

export const specimenGet = defineOperation({
  name: "specimen.get",
  input: z.object({ specimenId }),
  run: async ({ actor, input, tx }) => {
    const s = await requireSpecimen(tx, actor, "read", input.specimenId);
    return view(s, actor.kind === "user" ? actor.userId : null);
  },
});

export const specimenUpdate = defineOperation({
  name: "specimen.update",
  input: z.object({ specimenId, title: title.optional(), description: description.optional() }),
  run: async ({ actor, input, tx }) => {
    await requireSpecimen(tx, actor, "write", input.specimenId);
    const s = await updateSpecimen(tx, input.specimenId, {
      title: input.title,
      description: input.description,
    });
    if (!s) throw new Error("specimen vanished inside its own transaction");
    await appendDomainEvent(tx, { specimenId: s.id, type: "specimen.changed", payload: {} });
    return view(s, actor.kind === "user" ? actor.userId : null);
  },
});

export const specimenDelete = defineOperation({
  name: "specimen.delete",
  input: z.object({ specimenId }),
  run: async ({ actor, input, tx }) => {
    await requireSpecimen(tx, actor, "write", input.specimenId);
    await deleteSpecimen(tx, input.specimenId);
    return { deleted: true as const };
  },
});

/** Authorizes opening a specimen's event stream (the SSE route runs it before streaming). */
export const specimenEventsOpen = defineOperation({
  name: "specimen.events.open",
  input: z.object({ specimenId }),
  run: async ({ actor, input, tx }) => {
    const s = await requireSpecimen(tx, actor, "read", input.specimenId);
    return { specimenId: s.id };
  },
});
