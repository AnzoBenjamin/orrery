CREATE TYPE "public"."footage_role" AS ENUM('reference', 'broken', 'repaired', 'supplementary', 'archival');--> statement-breakpoint
CREATE TYPE "public"."footage_status" AS ENUM('uploading', 'probing', 'ready', 'rejected');--> statement-breakpoint
CREATE TYPE "public"."share_scope" AS ENUM('read');--> statement-breakpoint
CREATE TYPE "public"."unit_system" AS ENUM('metric', 'imperial');--> statement-breakpoint
CREATE TABLE "account" (
	"id" uuid PRIMARY KEY DEFAULT uuidv7() NOT NULL,
	"account_id" text NOT NULL,
	"provider_id" text NOT NULL,
	"user_id" uuid NOT NULL,
	"access_token" text,
	"refresh_token" text,
	"id_token" text,
	"access_token_expires_at" timestamp with time zone,
	"refresh_token_expires_at" timestamp with time zone,
	"scope" text,
	"password" text,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone NOT NULL
);
--> statement-breakpoint
CREATE TABLE "passkey" (
	"id" uuid PRIMARY KEY DEFAULT uuidv7() NOT NULL,
	"name" text,
	"public_key" text NOT NULL,
	"user_id" uuid NOT NULL,
	"credential_id" text NOT NULL,
	"counter" integer NOT NULL,
	"device_type" text NOT NULL,
	"backed_up" boolean NOT NULL,
	"transports" text,
	"created_at" timestamp with time zone,
	"aaguid" text
);
--> statement-breakpoint
CREATE TABLE "rate_limit" (
	"id" uuid PRIMARY KEY DEFAULT uuidv7() NOT NULL,
	"key" text NOT NULL,
	"count" integer NOT NULL,
	"last_request" bigint NOT NULL,
	CONSTRAINT "rate_limit_key_unique" UNIQUE("key")
);
--> statement-breakpoint
CREATE TABLE "session" (
	"id" uuid PRIMARY KEY DEFAULT uuidv7() NOT NULL,
	"expires_at" timestamp with time zone NOT NULL,
	"token" text NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone NOT NULL,
	"ip_address" text,
	"user_agent" text,
	"user_id" uuid NOT NULL,
	CONSTRAINT "session_token_unique" UNIQUE("token")
);
--> statement-breakpoint
CREATE TABLE "user" (
	"id" uuid PRIMARY KEY DEFAULT uuidv7() NOT NULL,
	"name" text NOT NULL,
	"email" text NOT NULL,
	"email_verified" boolean DEFAULT false NOT NULL,
	"image" text,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	"role" text DEFAULT 'user' NOT NULL,
	CONSTRAINT "user_email_unique" UNIQUE("email")
);
--> statement-breakpoint
CREATE TABLE "verification" (
	"id" uuid PRIMARY KEY DEFAULT uuidv7() NOT NULL,
	"identifier" text NOT NULL,
	"value" text NOT NULL,
	"expires_at" timestamp with time zone NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "domain_event" (
	"id" bigserial PRIMARY KEY NOT NULL,
	"specimen_id" uuid NOT NULL,
	"type" text NOT NULL,
	"payload" jsonb NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "footage" (
	"id" uuid PRIMARY KEY DEFAULT uuidv7() NOT NULL,
	"specimen_id" uuid NOT NULL,
	"role" "footage_role" NOT NULL,
	"status" "footage_status" DEFAULT 'uploading' NOT NULL,
	"object_key" text NOT NULL,
	"original_filename" text NOT NULL,
	"byte_size" bigint NOT NULL,
	"sha256" text,
	"duration_s" double precision,
	"width" integer,
	"height" integer,
	"fps_nominal" double precision,
	"is_vfr" boolean,
	"codec" text,
	"rotation_quarter_turns" smallint,
	"rejection_reason" text,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "footage_byte_size" CHECK ("footage"."byte_size" >= 0),
	CONSTRAINT "footage_sha256_format" CHECK ("footage"."sha256" ~ '^[0-9a-f]{64}$'),
	CONSTRAINT "footage_duration" CHECK ("footage"."duration_s" > 0),
	CONSTRAINT "footage_dimensions" CHECK ("footage"."width" > 0 and "footage"."height" > 0),
	CONSTRAINT "footage_fps" CHECK ("footage"."fps_nominal" > 0),
	CONSTRAINT "footage_rotation" CHECK ("footage"."rotation_quarter_turns" between 0 and 3),
	CONSTRAINT "footage_rejection_reason" CHECK (("footage"."status" = 'rejected') = ("footage"."rejection_reason" is not null))
);
--> statement-breakpoint
CREATE TABLE "notification" (
	"id" uuid PRIMARY KEY DEFAULT uuidv7() NOT NULL,
	"user_id" uuid NOT NULL,
	"kind" text NOT NULL,
	"payload" jsonb NOT NULL,
	"read_at" timestamp with time zone,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "object_deletion" (
	"id" uuid PRIMARY KEY DEFAULT uuidv7() NOT NULL,
	"object_key" text NOT NULL,
	"attempts" integer DEFAULT 0 NOT NULL,
	"last_error" text,
	"completed_at" timestamp with time zone,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "object_deletion_attempts" CHECK ("object_deletion"."attempts" >= 0)
);
--> statement-breakpoint
CREATE TABLE "share_link" (
	"id" uuid PRIMARY KEY DEFAULT uuidv7() NOT NULL,
	"specimen_id" uuid NOT NULL,
	"token_hash" text NOT NULL,
	"scope" "share_scope" DEFAULT 'read' NOT NULL,
	"expires_at" timestamp with time zone,
	"revoked_at" timestamp with time zone,
	"created_by" uuid NOT NULL,
	"last_used_at" timestamp with time zone,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "share_link_token_hash_format" CHECK ("share_link"."token_hash" ~ '^[0-9a-f]{64}$')
);
--> statement-breakpoint
CREATE TABLE "specimen" (
	"id" uuid PRIMARY KEY DEFAULT uuidv7() NOT NULL,
	"owner_id" uuid NOT NULL,
	"title" text NOT NULL,
	"description" text DEFAULT '' NOT NULL,
	"cover_object_key" text,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "specimen_title_length" CHECK (char_length("specimen"."title") between 1 and 200),
	CONSTRAINT "specimen_description_length" CHECK (char_length("specimen"."description") <= 5000)
);
--> statement-breakpoint
CREATE TABLE "upload_session" (
	"id" uuid PRIMARY KEY DEFAULT uuidv7() NOT NULL,
	"footage_id" uuid NOT NULL,
	"s3_upload_id" text NOT NULL,
	"part_size" integer NOT NULL,
	"expires_at" timestamp with time zone NOT NULL,
	"completed_at" timestamp with time zone,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "upload_session_part_size" CHECK ("upload_session"."part_size" between 5242880 and 2147483647)
);
--> statement-breakpoint
CREATE TABLE "user_preference" (
	"user_id" uuid PRIMARY KEY NOT NULL,
	"analysis_complete_email" boolean DEFAULT true NOT NULL,
	"sound_enabled" boolean DEFAULT false NOT NULL,
	"units" "unit_system" DEFAULT 'metric' NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
ALTER TABLE "account" ADD CONSTRAINT "account_user_id_user_id_fk" FOREIGN KEY ("user_id") REFERENCES "public"."user"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "passkey" ADD CONSTRAINT "passkey_user_id_user_id_fk" FOREIGN KEY ("user_id") REFERENCES "public"."user"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "session" ADD CONSTRAINT "session_user_id_user_id_fk" FOREIGN KEY ("user_id") REFERENCES "public"."user"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "domain_event" ADD CONSTRAINT "domain_event_specimen_id_specimen_id_fk" FOREIGN KEY ("specimen_id") REFERENCES "public"."specimen"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "footage" ADD CONSTRAINT "footage_specimen_id_specimen_id_fk" FOREIGN KEY ("specimen_id") REFERENCES "public"."specimen"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "notification" ADD CONSTRAINT "notification_user_id_user_id_fk" FOREIGN KEY ("user_id") REFERENCES "public"."user"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "share_link" ADD CONSTRAINT "share_link_specimen_id_specimen_id_fk" FOREIGN KEY ("specimen_id") REFERENCES "public"."specimen"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "share_link" ADD CONSTRAINT "share_link_created_by_user_id_fk" FOREIGN KEY ("created_by") REFERENCES "public"."user"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "specimen" ADD CONSTRAINT "specimen_owner_id_user_id_fk" FOREIGN KEY ("owner_id") REFERENCES "public"."user"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "upload_session" ADD CONSTRAINT "upload_session_footage_id_footage_id_fk" FOREIGN KEY ("footage_id") REFERENCES "public"."footage"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "user_preference" ADD CONSTRAINT "user_preference_user_id_user_id_fk" FOREIGN KEY ("user_id") REFERENCES "public"."user"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "account_userId_idx" ON "account" USING btree ("user_id");--> statement-breakpoint
CREATE INDEX "passkey_userId_idx" ON "passkey" USING btree ("user_id");--> statement-breakpoint
CREATE INDEX "passkey_credentialID_idx" ON "passkey" USING btree ("credential_id");--> statement-breakpoint
CREATE INDEX "session_userId_idx" ON "session" USING btree ("user_id");--> statement-breakpoint
CREATE INDEX "verification_identifier_idx" ON "verification" USING btree ("identifier");--> statement-breakpoint
CREATE INDEX "domain_event_specimen_idx" ON "domain_event" USING btree ("specimen_id","id");--> statement-breakpoint
CREATE UNIQUE INDEX "footage_object_key_idx" ON "footage" USING btree ("object_key");--> statement-breakpoint
CREATE INDEX "footage_specimen_idx" ON "footage" USING btree ("specimen_id","id");--> statement-breakpoint
CREATE INDEX "notification_user_idx" ON "notification" USING btree ("user_id","id");--> statement-breakpoint
CREATE INDEX "notification_unread_idx" ON "notification" USING btree ("user_id") WHERE "notification"."read_at" is null;--> statement-breakpoint
CREATE INDEX "object_deletion_pending_idx" ON "object_deletion" USING btree ("created_at") WHERE "object_deletion"."completed_at" is null;--> statement-breakpoint
CREATE UNIQUE INDEX "share_link_token_hash_idx" ON "share_link" USING btree ("token_hash");--> statement-breakpoint
CREATE INDEX "share_link_specimen_idx" ON "share_link" USING btree ("specimen_id","id");--> statement-breakpoint
CREATE INDEX "specimen_owner_idx" ON "specimen" USING btree ("owner_id","id");--> statement-breakpoint
CREATE UNIQUE INDEX "upload_session_footage_idx" ON "upload_session" USING btree ("footage_id");--> statement-breakpoint
CREATE INDEX "upload_session_open_idx" ON "upload_session" USING btree ("expires_at") WHERE "upload_session"."completed_at" is null;