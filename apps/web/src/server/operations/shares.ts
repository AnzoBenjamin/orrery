import { createHash, randomBytes } from "node:crypto";
import {
  createShareLink,
  findShareLinkById,
  listFootageForSpecimen,
  listShareLinks,
  resolveShareLink,
  revokeShareLink,
  type ShareLink,
} from "@orrery/db";
import { z } from "zod";
import type { Actor } from "../actor.ts";
import { DomainError, notFound } from "../domain-errors.ts";
import { requireFootage, requireSpecimen } from "../policy.ts";
import { defineOperation, type OperationContext } from "./define.ts";
import { type FootageView, footageView } from "./footage.ts";

// Read-only share links (requirement 5.3). The token is 32 random bytes, shown once to the owner
// and stored only as its SHA-256. Opening a link turns the visitor into a share actor for that one
// specimen, and every read still goes through policy.ts.

const PLAYBACK_URL_SECONDS = 15 * 60;
const DAY_MS = 24 * 60 * 60 * 1000;

const token = z
  .string()
  .regex(/^[A-Za-z0-9_-]{43}$/, "This share link is not valid. Check that it was copied whole.");

export const hashShareToken = (value: string) => createHash("sha256").update(value).digest("hex");

export interface ShareLinkView {
  id: string;
  createdAt: string;
  expiresAt: string | null;
  revokedAt: string | null;
  lastUsedAt: string | null;
  active: boolean;
}

function view(link: ShareLink, now: Date): ShareLinkView {
  return {
    id: link.id,
    createdAt: link.createdAt.toISOString(),
    expiresAt: link.expiresAt?.toISOString() ?? null,
    revokedAt: link.revokedAt?.toISOString() ?? null,
    lastUsedAt: link.lastUsedAt?.toISOString() ?? null,
    active: !link.revokedAt && (!link.expiresAt || link.expiresAt > now),
  };
}

/** The share actor for a token, after the per-address rate limit. NotFound for any bad token. */
async function shareActor(
  ctx: Pick<OperationContext<unknown>, "tx" | "services" | "request">,
  value: string,
): Promise<Extract<Actor, { kind: "share" }>> {
  await ctx.services.limit("share-access", ctx.request.ip ?? "unknown");
  const link = await resolveShareLink(ctx.tx, hashShareToken(value), new Date());
  if (!link) throw notFound("That shared specimen");
  return { kind: "share", specimenId: link.specimenId, shareLinkId: link.id };
}

export const shareList = defineOperation({
  name: "share.list",
  input: z.object({ specimenId: z.uuid("That specimen does not exist.") }),
  run: async ({ actor, input, tx }) => {
    await requireSpecimen(tx, actor, "write", input.specimenId);
    const now = new Date();
    return (await listShareLinks(tx, input.specimenId)).map((l) => view(l, now));
  },
});

export const shareCreate = defineOperation({
  name: "share.create",
  input: z.object({
    specimenId: z.uuid("That specimen does not exist."),
    /** Days until the link stops working; omit for a link that lasts until revoked. */
    expiresInDays: z.number().int().min(1).max(365).optional(),
  }),
  run: async ({ actor, input, tx }) => {
    const specimen = await requireSpecimen(tx, actor, "write", input.specimenId);
    if (actor.kind !== "user") throw notFound("That specimen");
    const secret = randomBytes(32).toString("base64url");
    const link = await createShareLink(tx, {
      specimenId: specimen.id,
      tokenHash: hashShareToken(secret),
      createdBy: actor.userId,
      expiresAt: input.expiresInDays
        ? new Date(Date.now() + input.expiresInDays * DAY_MS)
        : undefined,
    });
    return { link: view(link, new Date()), token: secret };
  },
});

export const shareRevoke = defineOperation({
  name: "share.revoke",
  input: z.object({ shareLinkId: z.uuid("That link does not exist.") }),
  run: async ({ actor, input, tx }) => {
    const link = await findShareLinkById(tx, input.shareLinkId);
    if (!link) throw notFound("That link");
    await requireSpecimen(tx, actor, "write", link.specimenId);
    const revoked = await revokeShareLink(tx, { id: link.id, specimenId: link.specimenId });
    return view(revoked ?? link, new Date());
  },
});

/** What a visitor with a share link sees: the specimen and its checked footage. */
export interface SharedSpecimenView {
  title: string;
  description: string;
  footage: FootageView[];
}

export const shareOpen = defineOperation({
  name: "share.open",
  input: z.object({ token }),
  run: async (ctx): Promise<SharedSpecimenView> => {
    const actor = await shareActor(ctx, ctx.input.token);
    const specimen = await requireSpecimen(ctx.tx, actor, "read", actor.specimenId);
    const footage = await listFootageForSpecimen(ctx.tx, specimen.id);
    return {
      title: specimen.title,
      description: specimen.description,
      footage: footage.filter((f) => f.status === "ready").map(footageView),
    };
  },
});

export const sharePlayback = defineOperation({
  name: "share.playback",
  input: z.object({ token, footageId: z.uuid("That footage does not exist.") }),
  run: async (ctx) => {
    const actor = await shareActor(ctx, ctx.input.token);
    const { footage } = await requireFootage(ctx.tx, actor, "read", ctx.input.footageId);
    if (footage.status !== "ready")
      throw new DomainError("NotFound", "That footage is not available.");
    const url = await ctx.services.storage.presignGet(footage.objectKey, PLAYBACK_URL_SECONDS);
    return { url, expiresInSeconds: PLAYBACK_URL_SECONDS };
  },
});
