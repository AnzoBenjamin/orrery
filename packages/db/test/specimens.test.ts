import { inArray } from "drizzle-orm";
import fc from "fast-check";
import { describe, expect, it } from "vitest";
import {
  countPendingDeletions,
  countSpecimensForOwner,
  createFootage,
  createSpecimen,
  deleteSpecimen,
  deleteSpecimensForOwner,
  findSpecimenById,
  listSpecimensForOwner,
  newId,
  updateSpecimen,
} from "../src/index.ts";
import { objectDeletion } from "../src/schema/index.ts";
import { insertUser, useTestDatabase } from "./support.ts";

const database = useTestDatabase();

describe("specimens", () => {
  it("creates, reads, and updates a specimen", async () => {
    const owner = await insertUser(database());
    const created = await createSpecimen(database().db, {
      ownerId: owner.id,
      title: "Singer 15-91",
    });
    expect(created.description).toBe("");
    expect(await findSpecimenById(database().db, created.id)).toEqual(created);

    const updated = await updateSpecimen(database().db, created.id, {
      description: "Hand crank sewing machine, bobbin winder seized.",
    });
    expect(updated?.title).toBe("Singer 15-91");
    expect(updated?.description).toBe("Hand crank sewing machine, bobbin winder seized.");
    expect(await updateSpecimen(database().db, newId(), { title: "x" })).toBeUndefined();
  });

  it("lists only the owner's specimens", async () => {
    const a = await insertUser(database());
    const b = await insertUser(database());
    await createSpecimen(database().db, { ownerId: a.id, title: "A's clock" });
    await createSpecimen(database().db, { ownerId: b.id, title: "B's loom" });
    const page = await listSpecimensForOwner(database().db, a.id, { limit: 10 });
    expect(page.items.map((s) => s.title)).toEqual(["A's clock"]);
    expect(await countSpecimensForOwner(database().db, b.id)).toBe(1);
  });

  it("pages through every specimen exactly once, newest first, for any page size", async () => {
    const owner = await insertUser(database());
    const created: string[] = [];
    for (let i = 0; i < 23; i += 1) {
      created.push((await createSpecimen(database().db, { ownerId: owner.id, title: `S${i}` })).id);
    }
    await fc.assert(
      fc.asyncProperty(fc.integer({ min: 1, max: 30 }), async (limit) => {
        const seen: string[] = [];
        let before: string | undefined;
        do {
          const page = await listSpecimensForOwner(database().db, owner.id, { limit, before });
          expect(page.items.length).toBeLessThanOrEqual(limit);
          seen.push(...page.items.map((s) => s.id));
          before = page.nextCursor;
        } while (before);
        expect(seen).toEqual([...created].reverse());
      }),
      { numRuns: 15 },
    );
  });

  it("deletes a specimen with its footage and queues the stored objects", async () => {
    const owner = await insertUser(database());
    const s = await createSpecimen(database().db, { ownerId: owner.id, title: "Automaton" });
    for (const name of ["ref.mp4", "broken.mp4"]) {
      await createFootage(database().db, {
        id: newId(),
        specimenId: s.id,
        role: "reference",
        objectKey: `users/${owner.id}/specimens/${s.id}/footage/${name}`,
        originalFilename: name,
        byteSize: 100,
      });
    }
    const pendingBefore = await countPendingDeletions(database().db);
    expect(await deleteSpecimen(database().db, s.id)).toBe(true);
    expect(await findSpecimenById(database().db, s.id)).toBeUndefined();
    expect(await countPendingDeletions(database().db)).toBe(pendingBefore + 2);
    expect(await deleteSpecimen(database().db, s.id)).toBe(false);
  });

  it("deletes every specimen of one owner, queues all their objects, and spares other owners", async () => {
    const owner = await insertUser(database());
    const bystander = await insertUser(database());
    const keys: string[] = [];
    for (const title of ["Loom", "Clock"]) {
      const s = await createSpecimen(database().db, { ownerId: owner.id, title });
      const key = `users/${owner.id}/specimens/${s.id}/footage/ref.mp4`;
      keys.push(key);
      await createFootage(database().db, {
        id: newId(),
        specimenId: s.id,
        role: "reference",
        objectKey: key,
        originalFilename: "ref.mp4",
        byteSize: 100,
      });
    }
    const kept = await createSpecimen(database().db, { ownerId: bystander.id, title: "Toy" });

    expect(await deleteSpecimensForOwner(database().db, owner.id)).toBe(2);
    expect(await countSpecimensForOwner(database().db, owner.id)).toBe(0);
    expect(await findSpecimenById(database().db, kept.id)).toBeDefined();
    const queued = await database()
      .db.select({ objectKey: objectDeletion.objectKey })
      .from(objectDeletion)
      .where(inArray(objectDeletion.objectKey, keys));
    expect(queued.map((q) => q.objectKey).sort()).toEqual([...keys].sort());
    expect(await deleteSpecimensForOwner(database().db, owner.id)).toBe(0);
  });
});
