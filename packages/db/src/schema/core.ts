import { sql } from "drizzle-orm";
import {
  bigint,
  bigserial,
  boolean,
  check,
  doublePrecision,
  index,
  integer,
  jsonb,
  pgEnum,
  pgTable,
  smallint,
  text,
  uniqueIndex,
  uuid,
} from "drizzle-orm/pg-core";
import { user } from "./auth.ts";
import { createdAt, id, timestamptz, updatedAt } from "./columns.ts";

// Core tables owned by platform-foundation (design: "Core tables owned by this spec").
// Quantities are SI (seconds); byte counts are integers. Times are timestamptz.
// Lists page by `id`: UUIDv7 sorts by creation time and, unlike timestamptz, survives a round trip
// through a JavaScript Date without losing precision.

export const unitSystem = pgEnum("unit_system", ["metric", "imperial"]);

export const userPreference = pgTable("user_preference", {
  userId: uuid("user_id")
    .primaryKey()
    .references(() => user.id, { onDelete: "cascade" }),
  analysisCompleteEmail: boolean("analysis_complete_email").default(true).notNull(),
  soundEnabled: boolean("sound_enabled").default(false).notNull(),
  /** Display units only. Stored data is always SI. */
  units: unitSystem("units").default("metric").notNull(),
  updatedAt: updatedAt(),
});

export const specimen = pgTable(
  "specimen",
  {
    id: id(),
    ownerId: uuid("owner_id")
      .notNull()
      .references(() => user.id, { onDelete: "cascade" }),
    title: text("title").notNull(),
    description: text("description").default("").notNull(),
    coverObjectKey: text("cover_object_key"),
    createdAt: createdAt(),
    updatedAt: updatedAt(),
  },
  (t) => [
    index("specimen_owner_idx").on(t.ownerId, t.id),
    check("specimen_title_length", sql`char_length(${t.title}) between 1 and 200`),
    check("specimen_description_length", sql`char_length(${t.description}) <= 5000`),
  ],
);

export const footageRole = pgEnum("footage_role", [
  "reference",
  "broken",
  "repaired",
  "supplementary",
  "archival",
]);

export const footageStatus = pgEnum("footage_status", [
  "uploading",
  "probing",
  "ready",
  "rejected",
]);

export const footage = pgTable(
  "footage",
  {
    id: id(),
    specimenId: uuid("specimen_id")
      .notNull()
      .references(() => specimen.id, { onDelete: "cascade" }),
    role: footageRole("role").notNull(),
    status: footageStatus("status").default("uploading").notNull(),
    objectKey: text("object_key").notNull(),
    originalFilename: text("original_filename").notNull(),
    byteSize: bigint("byte_size", { mode: "number" }).notNull(),
    /** Lowercase hex SHA-256 of the object, set when probing completes. */
    sha256: text("sha256"),
    durationS: doublePrecision("duration_s"),
    width: integer("width"),
    height: integer("height"),
    fpsNominal: doublePrecision("fps_nominal"),
    isVfr: boolean("is_vfr"),
    codec: text("codec"),
    /** Display rotation from container metadata, in counter-clockwise quarter turns (0 to 3). */
    rotationQuarterTurns: smallint("rotation_quarter_turns"),
    rejectionReason: text("rejection_reason"),
    createdAt: createdAt(),
    updatedAt: updatedAt(),
  },
  (t) => [
    uniqueIndex("footage_object_key_idx").on(t.objectKey),
    index("footage_specimen_idx").on(t.specimenId, t.id),
    check("footage_byte_size", sql`${t.byteSize} >= 0`),
    check("footage_sha256_format", sql`${t.sha256} ~ '^[0-9a-f]{64}$'`),
    check("footage_duration", sql`${t.durationS} > 0`),
    check("footage_dimensions", sql`${t.width} > 0 and ${t.height} > 0`),
    check("footage_fps", sql`${t.fpsNominal} > 0`),
    check("footage_rotation", sql`${t.rotationQuarterTurns} between 0 and 3`),
    check(
      "footage_rejection_reason",
      sql`(${t.status} = 'rejected') = (${t.rejectionReason} is not null)`,
    ),
  ],
);

export const uploadSession = pgTable(
  "upload_session",
  {
    id: id(),
    footageId: uuid("footage_id")
      .notNull()
      .references(() => footage.id, { onDelete: "cascade" }),
    s3UploadId: text("s3_upload_id").notNull(),
    /** Bytes per part. S3 requires 5 MiB to 5 GiB for every part except the last. */
    partSize: integer("part_size").notNull(),
    expiresAt: timestamptz("expires_at").notNull(),
    completedAt: timestamptz("completed_at"),
    createdAt: createdAt(),
  },
  (t) => [
    uniqueIndex("upload_session_footage_idx").on(t.footageId),
    index("upload_session_open_idx").on(t.expiresAt).where(sql`${t.completedAt} is null`),
    check("upload_session_part_size", sql`${t.partSize} between 5242880 and 2147483647`),
  ],
);

export const shareScope = pgEnum("share_scope", ["read"]);

export const shareLink = pgTable(
  "share_link",
  {
    id: id(),
    specimenId: uuid("specimen_id")
      .notNull()
      .references(() => specimen.id, { onDelete: "cascade" }),
    /** SHA-256 of the token, lowercase hex. The token itself is shown once and never stored. */
    tokenHash: text("token_hash").notNull(),
    scope: shareScope("scope").default("read").notNull(),
    expiresAt: timestamptz("expires_at"),
    revokedAt: timestamptz("revoked_at"),
    createdBy: uuid("created_by")
      .notNull()
      .references(() => user.id, { onDelete: "cascade" }),
    lastUsedAt: timestamptz("last_used_at"),
    createdAt: createdAt(),
  },
  (t) => [
    uniqueIndex("share_link_token_hash_idx").on(t.tokenHash),
    index("share_link_specimen_idx").on(t.specimenId, t.id),
    check("share_link_token_hash_format", sql`${t.tokenHash} ~ '^[0-9a-f]{64}$'`),
  ],
);

/** Append-only event log per specimen. Feeds SSE and its Last-Event-ID replay. */
export const domainEvent = pgTable(
  "domain_event",
  {
    id: bigserial("id", { mode: "number" }).primaryKey(),
    specimenId: uuid("specimen_id")
      .notNull()
      .references(() => specimen.id, { onDelete: "cascade" }),
    type: text("type").notNull(),
    payload: jsonb("payload").$type<Record<string, unknown>>().notNull(),
    createdAt: createdAt(),
  },
  (t) => [index("domain_event_specimen_idx").on(t.specimenId, t.id)],
);

export const notification = pgTable(
  "notification",
  {
    id: id(),
    userId: uuid("user_id")
      .notNull()
      .references(() => user.id, { onDelete: "cascade" }),
    kind: text("kind").notNull(),
    payload: jsonb("payload").$type<Record<string, unknown>>().notNull(),
    readAt: timestamptz("read_at"),
    createdAt: createdAt(),
  },
  (t) => [
    index("notification_user_idx").on(t.userId, t.id),
    index("notification_unread_idx").on(t.userId).where(sql`${t.readAt} is null`),
  ],
);

/**
 * Objects awaiting deletion from storage. Rows outlive the records that referenced the objects,
 * so there is no foreign key.
 */
export const objectDeletion = pgTable(
  "object_deletion",
  {
    id: id(),
    objectKey: text("object_key").notNull(),
    attempts: integer("attempts").default(0).notNull(),
    lastError: text("last_error"),
    completedAt: timestamptz("completed_at"),
    createdAt: createdAt(),
  },
  (t) => [
    index("object_deletion_pending_idx").on(t.createdAt).where(sql`${t.completedAt} is null`),
    check("object_deletion_attempts", sql`${t.attempts} >= 0`),
  ],
);
