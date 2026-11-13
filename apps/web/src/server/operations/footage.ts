import {
  appendDomainEvent,
  completeUploadSession,
  createFootage,
  createUploadSession,
  deleteFootage,
  type Executor,
  type Footage,
  findUploadSession,
  listFootageForSpecimen,
  markFootageProbing,
  markFootageRejected,
  newId,
  storageBytesForOwner,
} from "@orrery/db";
import { footageProbe } from "@orrery/jobs";
import {
  footageObjectKey,
  MAX_FOOTAGE_BYTES,
  MAX_PARTS,
  partCount,
  partSizeFor,
  UPLOAD_TTL_SECONDS,
} from "@orrery/storage";
import { z } from "zod";
import { DomainError } from "../domain-errors.ts";
import { requireFootage, requireSpecimen, requireUser, requireVerifiedUser } from "../policy.ts";
import { defineOperation, type OperationContext } from "./define.ts";

export const FOOTAGE_ROLES = [
  "reference",
  "broken",
  "repaired",
  "supplementary",
  "archival",
] as const;
export type FootageRoleName = (typeof FOOTAGE_ROLES)[number];

/** Upload URLs are signed for this long. A part of 8 MiB on a slow phone link fits easily. */
const PART_URL_SECONDS = 10 * 60;
/** Playback URLs are signed for this long; the player asks for a new one when it expires. */
const PLAYBACK_URL_SECONDS = 15 * 60;

const footageId = z.uuid("That footage does not exist.");
const specimenId = z.uuid("That specimen does not exist.");

/** What the UI sees of a footage item. Durations are seconds; dates are ISO strings. */
export interface FootageView {
  id: string;
  specimenId: string;
  role: FootageRoleName;
  status: Footage["status"];
  filename: string;
  byteSize: number;
  durationS: number | null;
  width: number | null;
  height: number | null;
  fpsNominal: number | null;
  isVfr: boolean | null;
  codec: string | null;
  rotationQuarterTurns: number | null;
  rejectionReason: string | null;
  createdAt: string;
}

export function footageView(f: Footage): FootageView {
  return {
    id: f.id,
    specimenId: f.specimenId,
    role: f.role,
    status: f.status,
    filename: f.originalFilename,
    byteSize: f.byteSize,
    durationS: f.durationS,
    width: f.width,
    height: f.height,
    fpsNominal: f.fpsNominal,
    isVfr: f.isVfr,
    codec: f.codec,
    rotationQuarterTurns: f.rotationQuarterTurns,
    rejectionReason: f.rejectionReason,
    createdAt: f.createdAt.toISOString(),
  };
}

/** Tells the specimen's live viewers (SSE) that this footage changed. */
function footageChanged(
  tx: Executor,
  specimenId: string,
  footageId: string,
  status: Footage["status"] | "deleted",
) {
  return appendDomainEvent(tx, {
    specimenId,
    type: "footage.changed",
    payload: { footageId, status },
  });
}

const gb = (bytes: number) => `${(bytes / 1e9).toFixed(1)} GB`;

export const footageList = defineOperation({
  name: "footage.list",
  input: z.object({ specimenId }),
  run: async ({ actor, input, tx }) => {
    await requireSpecimen(tx, actor, "read", input.specimenId);
    return (await listFootageForSpecimen(tx, input.specimenId)).map(footageView);
  },
});

/** Storage used against the quota, shown in account settings and before uploading. */
export const footageUsage = defineOperation({
  name: "footage.usage",
  input: z.object({}),
  run: async ({ actor, tx, services }) => {
    const user = requireUser(actor);
    return {
      usedBytes: await storageBytesForOwner(tx, user.userId),
      quotaBytes: services.quotaBytes,
    };
  },
});

export const footageUploadCreate = defineOperation({
  name: "footage.upload.create",
  input: z.object({
    specimenId,
    role: z.enum(FOOTAGE_ROLES, "Choose what this footage shows."),
    filename: z
      .string()
      .trim()
      .min(1, "The file needs a name.")
      .max(255, "Rename the file to under 255 characters."),
    byteSize: z
      .number()
      .int()
      .min(1, "This file is empty.")
      .max(
        MAX_FOOTAGE_BYTES,
        "Footage must be 1 GB or smaller. Trim the clip or export it at a lower bitrate.",
      ),
  }),
  run: async ({ actor, input, tx, services }) => {
    const user = requireVerifiedUser(actor);
    const specimen = await requireSpecimen(tx, actor, "write", input.specimenId);
    const used = await storageBytesForOwner(tx, user.userId);
    if (used + input.byteSize > services.quotaBytes) {
      throw new DomainError(
        "Conflict",
        `This file would take you past your ${gb(services.quotaBytes)} of storage (${gb(used)} used). Delete footage you no longer need, then try again.`,
      );
    }
    const id = newId();
    const objectKey = footageObjectKey({
      userId: specimen.ownerId,
      specimenId: specimen.id,
      footageId: id,
      filename: input.filename,
    });
    await createFootage(tx, {
      id,
      specimenId: specimen.id,
      role: input.role,
      objectKey,
      originalFilename: input.filename,
      byteSize: input.byteSize,
    });
    await footageChanged(tx, specimen.id, id, "uploading");
    return { footageId: id, key: objectKey, partSize: partSizeFor(input.byteSize) };
  },
});

/** Footage whose upload is still open, with its multipart session once one has begun. */
async function uploading(ctx: Pick<OperationContext<unknown>, "actor" | "tx">, id: string) {
  requireVerifiedUser(ctx.actor);
  const { footage } = await requireFootage(ctx.tx, ctx.actor, "write", id);
  const expiresAt = new Date(footage.createdAt.getTime() + UPLOAD_TTL_SECONDS * 1000);
  if (footage.status !== "uploading" || expiresAt <= new Date()) {
    throw new DomainError(
      "Conflict",
      "This upload has finished or expired. Remove it and add the file again.",
    );
  }
  const session = await findUploadSession(ctx.tx, footage.id);
  return { footage, session, expiresAt };
}

const uploadId = z.string().min(1).max(1024);

/**
 * One S3 request of the browser's multipart upload (Uppy signs each request separately). The
 * key is always the footage's own, the upload id must be the one this footage started, and part
 * numbers stay within the declared size, so a signature can only ever write this file.
 */
const s3Request = z.discriminatedUnion("step", [
  z.object({ step: z.literal("create") }),
  z.object({
    step: z.literal("part"),
    uploadId,
    partNumber: z.number().int().min(1).max(MAX_PARTS),
  }),
  z.object({ step: z.literal("list-parts"), uploadId }),
  z.object({ step: z.literal("complete"), uploadId }),
  z.object({ step: z.literal("abort"), uploadId }),
]);

export const footageUploadSign = defineOperation({
  name: "footage.upload.sign",
  input: z.object({ footageId, request: s3Request }),
  run: async (ctx) => {
    const { footage, session, expiresAt } = await uploading(ctx, ctx.input.footageId);
    await ctx.services.limit("upload-sign", requireUser(ctx.actor).userId);
    const { storage } = ctx.services;
    const request = ctx.input.request;
    const key = footage.objectKey;
    const partSize = partSizeFor(footage.byteSize);

    if (request.step === "create") {
      if (session) {
        throw new DomainError("Conflict", "This upload has already started. Resume it instead.");
      }
      return { url: await storage.presignCreateMultipartUpload(key, PART_URL_SECONDS), key };
    }

    let current = session;
    if (!current) {
      // The browser started the upload itself; adopt its upload id once S3 confirms it exists
      // for this footage's key.
      const pending = await storage.listMultipartUploads(key);
      if (!pending.some((u) => u.key === key && u.uploadId === request.uploadId)) {
        throw new DomainError("Conflict", "That upload does not belong to this footage.");
      }
      current = await createUploadSession(ctx.tx, {
        footageId: footage.id,
        s3UploadId: request.uploadId,
        partSize,
        expiresAt,
      });
    }
    if (current.s3UploadId !== request.uploadId) {
      throw new DomainError("Conflict", "That upload does not belong to this footage.");
    }

    switch (request.step) {
      case "part":
        if (request.partNumber > partCount(footage.byteSize, current.partSize)) {
          throw new DomainError("Invalid", "That part is beyond the end of the file.");
        }
        return {
          url: await storage.presignUploadPart(
            key,
            request.uploadId,
            request.partNumber,
            PART_URL_SECONDS,
          ),
          key,
        };
      case "list-parts":
        return {
          url: await storage.presignListParts(key, request.uploadId, PART_URL_SECONDS),
          key,
        };
      case "complete":
        return {
          url: await storage.presignCompleteMultipartUpload(
            key,
            request.uploadId,
            PART_URL_SECONDS,
          ),
          key,
        };
      case "abort":
        return {
          url: await storage.presignAbortMultipartUpload(key, request.uploadId, PART_URL_SECONDS),
          key,
        };
    }
  },
});

/**
 * Called once the browser has assembled the object. The stored size must match the declared
 * size; then the footage moves to probing and the probe job is queued after commit.
 */
export const footageUploadComplete = defineOperation({
  name: "footage.upload.complete",
  input: z.object({ footageId }),
  run: async (ctx) => {
    const { footage, session } = await uploading(ctx, ctx.input.footageId);
    const stored = await ctx.services.storage.objectSize(footage.objectKey);
    if (stored === null) {
      throw new DomainError("Conflict", "The upload has not finished yet. Keep this page open.");
    }
    if (session) await completeUploadSession(ctx.tx, session.id);
    if (stored !== footage.byteSize) {
      const rejected = await markFootageRejected(
        ctx.tx,
        footage.id,
        "The upload arrived incomplete. Remove it and add the file again.",
      );
      await footageChanged(ctx.tx, footage.specimenId, footage.id, "rejected");
      return footageView(rejected ?? footage);
    }
    const probing = await markFootageProbing(ctx.tx, footage.id);
    await footageChanged(ctx.tx, footage.specimenId, footage.id, "probing");
    ctx.afterCommit(() => ctx.services.enqueue(footageProbe, { footageId: footage.id }));
    return footageView(probing ?? footage);
  },
});

/** Cancels an upload in progress and forgets the footage. */
export const footageUploadAbort = defineOperation({
  name: "footage.upload.abort",
  input: z.object({ footageId }),
  run: async ({ actor, input, tx, services }) => {
    const { footage } = await requireFootage(tx, actor, "write", input.footageId);
    if (footage.status === "uploading") {
      // Aborts every unfinished upload to this key, including one the browser started but never
      // reported. The object deletion queued below repeats this in the background.
      for (const upload of await services.storage.listMultipartUploads(footage.objectKey)) {
        if (upload.key === footage.objectKey) {
          await services.storage.abortMultipartUpload(upload.key, upload.uploadId);
        }
      }
    }
    await deleteFootage(tx, { id: footage.id, specimenId: footage.specimenId });
    await footageChanged(tx, footage.specimenId, footage.id, "deleted");
    return { removed: true as const };
  },
});

export const footageDelete = defineOperation({
  name: "footage.delete",
  input: z.object({ footageId }),
  run: async ({ actor, input, tx }) => {
    const { footage } = await requireFootage(tx, actor, "write", input.footageId);
    await deleteFootage(tx, { id: footage.id, specimenId: footage.specimenId });
    await footageChanged(tx, footage.specimenId, footage.id, "deleted");
    return { removed: true as const };
  },
});

/** A short-lived URL to play footage, after the access check (requirement 6.4). */
export const footagePlayback = defineOperation({
  name: "footage.playback",
  input: z.object({ footageId }),
  run: async ({ actor, input, tx, services }) => {
    const { footage } = await requireFootage(tx, actor, "read", input.footageId);
    if (footage.status !== "ready") {
      throw new DomainError("Conflict", "This footage cannot be played until it has been checked.");
    }
    const url = await services.storage.presignGet(footage.objectKey, PLAYBACK_URL_SECONDS);
    return { url, expiresInSeconds: PLAYBACK_URL_SECONDS };
  },
});
