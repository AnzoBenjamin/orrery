import { type Executor, findSpecimenById, type Specimen } from "@orrery/db";
import type { Actor } from "./actor.ts";
import { DomainError, notFound } from "./domain-errors.ts";

/**
 * The single authorization module (requirement 5.1). Every operation states the access it needs
 * and resolves resources only through these functions.
 */
export type SpecimenAction = "read" | "write";

export function can(actor: Actor, action: SpecimenAction, specimen: Specimen): boolean {
  switch (actor.kind) {
    case "user":
      return specimen.ownerId === actor.userId || (actor.isAdmin && action === "read");
    case "share":
      return action === "read" && actor.specimenId === specimen.id;
    case "anonymous":
      return false;
  }
}

/** Loads a specimen the actor may act on, or fails with NotFound whether it is missing or not theirs. */
export async function requireSpecimen(
  ex: Executor,
  actor: Actor,
  action: SpecimenAction,
  specimenId: string,
): Promise<Specimen> {
  const specimen = await findSpecimenById(ex, specimenId);
  if (!specimen || !can(actor, action, specimen)) throw notFound("That specimen");
  return specimen;
}

export type UserActor = Extract<Actor, { kind: "user" }>;

export function requireUser(actor: Actor): UserActor {
  if (actor.kind !== "user") {
    throw new DomainError("Unauthenticated", "Sign in to continue.");
  }
  return actor;
}

export function requireAdmin(actor: Actor): UserActor {
  const user = requireUser(actor);
  if (!user.isAdmin) throw notFound("That page");
  return user;
}
