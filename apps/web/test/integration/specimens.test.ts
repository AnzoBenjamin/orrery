import { describe, expect, it } from "vitest";
import { anonymous } from "../../src/server/actor.ts";
import { invoke } from "../../src/server/operations/define.ts";
import {
  specimenCreate,
  specimenDelete,
  specimenGet,
  specimenList,
  specimenUpdate,
} from "../../src/server/operations/specimens.ts";
import { userActor, withTestDatabase } from "./support.ts";

const database = withTestDatabase();

describe("specimen operations", () => {
  it("create, get, rename, list, and delete for the owner", async () => {
    const owner = await userActor(database());
    const created = await invoke(database().db, specimenCreate, owner, {
      title: "  Singer 66 treadle  ",
      description: "Bobbin winder seized.",
    });
    if (!created.ok) throw new Error(created.error.message);
    expect(created.value).toMatchObject({ title: "Singer 66 treadle", isOwner: true });

    const id = created.value.id;
    const got = await invoke(database().db, specimenGet, owner, { specimenId: id });
    expect(got).toMatchObject({ ok: true, value: { id } });

    const renamed = await invoke(database().db, specimenUpdate, owner, {
      specimenId: id,
      title: "Singer 66, 1923",
    });
    expect(renamed).toMatchObject({ ok: true, value: { title: "Singer 66, 1923" } });

    const list = await invoke(database().db, specimenList, owner, {});
    expect(list.ok && list.value.items.map((s) => s.id)).toEqual([id]);

    expect(await invoke(database().db, specimenDelete, owner, { specimenId: id })).toEqual({
      ok: true,
      value: { deleted: true },
    });
    expect(await invoke(database().db, specimenGet, owner, { specimenId: id })).toMatchObject({
      ok: false,
      error: { kind: "NotFound" },
    });
  });

  it("rejects invalid and unknown input with per-field messages", async () => {
    const owner = await userActor(database());
    const empty = await invoke(database().db, specimenCreate, owner, { title: "   " });
    expect(empty).toMatchObject({
      ok: false,
      error: { kind: "Invalid", fields: { title: "Give the specimen a name." } },
    });
    const extra = await invoke(database().db, specimenCreate, owner, {
      title: "Loom",
      ownerId: owner.userId,
    });
    expect(extra).toMatchObject({ ok: false, error: { kind: "Invalid" } });
  });

  it("requires a signed-in user", async () => {
    expect(await invoke(database().db, specimenList, anonymous, {})).toMatchObject({
      ok: false,
      error: { kind: "Unauthenticated" },
    });
  });

  it("reports unexpected failures with a reference and no internals", async () => {
    const owner = await userActor(database());
    const failing = { ...specimenGet, run: async () => Promise.reject(new Error("pool exploded")) };
    const result = await invoke(
      database().db,
      failing,
      owner,
      { specimenId: crypto.randomUUID() },
      {
        report: () => "ref12345",
      },
    );
    expect(result).toEqual({
      ok: false,
      error: {
        kind: "Unavailable",
        message: "Something went wrong on our side. Try again in a moment.",
        reference: "ref12345",
      },
    });
  });
});
