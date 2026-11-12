import { eq, sql } from "drizzle-orm";
import { describe, expect, it } from "vitest";
import { createFootage, createSpecimen, newId } from "../src/index.ts";
import { footage, specimen, user } from "../src/schema/index.ts";
import { insertUser, useTestDatabase } from "./support.ts";

const database = useTestDatabase();

const UUID_V7 = /^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

async function pgErrorOf(
  run: () => Promise<unknown>,
): Promise<{ code?: string; constraint?: string }> {
  try {
    await run();
  } catch (error) {
    const cause = (error as { cause?: unknown }).cause ?? error;
    return cause as { code?: string; constraint?: string };
  }
  throw new Error("expected the statement to fail");
}

describe("schema", () => {
  it("generates UUIDv7 primary keys in the database and in the application", async () => {
    const owner = await insertUser(database());
    const s = await createSpecimen(database().db, { ownerId: owner.id, title: "Singer 66" });
    expect(owner.id).toMatch(UUID_V7);
    expect(s.id).toMatch(UUID_V7);
    expect(newId()).toMatch(UUID_V7);
  });

  it("stores timestamps as timestamptz", async () => {
    const { rows } = await database().db.execute<{ data_type: string }>(sql`
      select distinct data_type from information_schema.columns
      where table_schema = 'public' and column_name like '%\\_at' escape '\\'
        and column_name <> 'last_request'`);
    expect(rows.map((r) => r.data_type)).toEqual(["timestamp with time zone"]);
  });

  it("gives every foreign key an explicit on-delete action", async () => {
    const { rows } = await database().db.execute<{ name: string; action: string }>(sql`
      select conname as name, confdeltype as action from pg_constraint
      where contype = 'f' and connamespace = 'public'::regnamespace`);
    expect(rows.length).toBeGreaterThan(0);
    for (const row of rows) expect(row.action, row.name).toBe("c");
  });

  it("removes a user's specimens and footage when the user is deleted", async () => {
    const owner = await insertUser(database());
    const s = await createSpecimen(database().db, { ownerId: owner.id, title: "Typewriter" });
    await createFootage(database().db, {
      id: newId(),
      specimenId: s.id,
      role: "reference",
      objectKey: `users/${owner.id}/specimens/${s.id}/footage/a.mp4`,
      originalFilename: "a.mp4",
      byteSize: 10,
    });
    await database().db.delete(user).where(eq(user.id, owner.id));
    expect(await database().db.select().from(specimen).where(eq(specimen.id, s.id))).toEqual([]);
    expect(await database().db.select().from(footage).where(eq(footage.specimenId, s.id))).toEqual(
      [],
    );
  });

  it("rejects an empty specimen title and a rejected status without a reason", async () => {
    const owner = await insertUser(database());
    expect(
      await pgErrorOf(() => createSpecimen(database().db, { ownerId: owner.id, title: "" })),
    ).toMatchObject({ code: "23514", constraint: "specimen_title_length" });

    const s = await createSpecimen(database().db, { ownerId: owner.id, title: "Loom" });
    const f = await createFootage(database().db, {
      id: newId(),
      specimenId: s.id,
      role: "broken",
      objectKey: `k/${newId()}`,
      originalFilename: "b.mov",
      byteSize: 1,
    });
    expect(
      await pgErrorOf(() =>
        database().db.update(footage).set({ status: "rejected" }).where(eq(footage.id, f.id)),
      ),
    ).toMatchObject({ code: "23514", constraint: "footage_rejection_reason" });
  });
});
