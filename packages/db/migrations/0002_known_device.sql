CREATE TABLE "known_device" (
	"id" uuid PRIMARY KEY DEFAULT uuidv7() NOT NULL,
	"user_id" uuid NOT NULL,
	"device" text NOT NULL,
	"ip_prefix" text NOT NULL,
	"first_seen_at" timestamp with time zone DEFAULT now() NOT NULL,
	"last_seen_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "known_device_device_length" CHECK (char_length("known_device"."device") between 1 and 200),
	CONSTRAINT "known_device_ip_prefix_length" CHECK (char_length("known_device"."ip_prefix") <= 64)
);
--> statement-breakpoint
ALTER TABLE "known_device" ADD CONSTRAINT "known_device_user_id_user_id_fk" FOREIGN KEY ("user_id") REFERENCES "public"."user"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
CREATE UNIQUE INDEX "known_device_user_device_network_idx" ON "known_device" USING btree ("user_id","device","ip_prefix");