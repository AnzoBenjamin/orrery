import { objectsDelete } from "@orrery/jobs";
import { describe, expect, it } from "vitest";
import { adminJobCancel, adminJobRetry, adminOverview } from "../../src/server/operations/admin.ts";
import { invoke } from "../../src/server/operations/define.ts";
import { userActor, withTestDatabase } from "./support.ts";

const database = withTestDatabase();

describe("operator operations", () => {
  it("shows queues and failures, retries a failed job, and cancels a queued one", async () => {
    const admin = { ...(await userActor(database())), isAdmin: true };
    const { boss } = database();
    await boss.send(objectsDelete.name, { payload: {}, traceparent: null });
    const [job] = await boss.fetch(objectsDelete.name);
    if (!job) throw new Error("no job fetched");
    await boss.fail(objectsDelete.name, job.id, new Error("storage unreachable"));

    const overview = await invoke(database().deps, adminOverview, admin, {});
    if (!overview.ok) throw new Error(overview.error.message);
    expect(overview.value.queues.map((q) => q.name)).toContain("footage.probe");
    expect(overview.value.queues.find((q) => q.name === objectsDelete.name)?.failed).toBe(1);
    expect(overview.value.failed).toMatchObject([
      { id: job.id, queue: objectsDelete.name, state: "failed", error: "storage unreachable" },
    ]);

    const input = { queue: objectsDelete.name, jobId: job.id };
    expect(await invoke(database().deps, adminJobRetry, admin, input)).toEqual({
      ok: true,
      value: { retried: true },
    });
    expect(await invoke(database().deps, adminJobRetry, admin, input)).toMatchObject({
      ok: false,
      error: { kind: "Conflict" },
    });
    expect(await invoke(database().deps, adminJobCancel, admin, input)).toEqual({
      ok: true,
      value: { cancelled: true },
    });
    expect(await invoke(database().deps, adminJobCancel, admin, input)).toMatchObject({
      ok: false,
      error: { kind: "Conflict" },
    });
  });

  it("does not exist for anyone but admins", async () => {
    const user = await userActor(database());
    expect(await invoke(database().deps, adminOverview, user, {})).toMatchObject({
      ok: false,
      error: { kind: "NotFound" },
    });
  });
});
