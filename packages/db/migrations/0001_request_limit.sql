CREATE TABLE "request_limit" (
	"key" varchar(255) PRIMARY KEY NOT NULL,
	"points" integer DEFAULT 0 NOT NULL,
	"expire" bigint
);
--> statement-breakpoint
CREATE INDEX "request_limit_expire_idx" ON "request_limit" USING btree ("expire");