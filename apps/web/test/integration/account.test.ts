import { randomBytes } from "node:crypto";
import { schema } from "@orrery/db";
import { describe, expect, it } from "vitest";
import { anonymous } from "../../src/server/actor.ts";
import { describeDevice } from "../../src/server/devices.ts";
import {
  accountGet,
  accountPreferencesUpdate,
  accountSessionRevoke,
  accountSessionsRevokeOthers,
} from "../../src/server/operations/account.ts";
import { invoke } from "../../src/server/operations/define.ts";
import { userActor, withTestDatabase } from "./support.ts";

const database = withTestDatabase();

async function anotherSession(userId: string, userAgent: string) {
  const [row] = await database()
    .db.insert(schema.session)
    .values({
      userId,
      token: randomBytes(24).toString("hex"),
      expiresAt: new Date(Date.now() + 3_600_000),
      updatedAt: new Date(Date.now() - 60_000),
      userAgent,
      ipAddress: "192.0.2.10",
    })
    .returning();
  if (!row) throw new Error("no session row");
  return row;
}

const FIREFOX_MAC =
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.5; rv:141.0) Gecko/20100101 Firefox/141.0";

describe("account operations", () => {
  it("shows the account with the current session first and defaults for preferences", async () => {
    const user = await userActor(database());
    const other = await anotherSession(user.userId, FIREFOX_MAC);

    const result = await invoke(database().deps, accountGet, user, {});
    if (!result.ok) throw new Error(result.error.message);
    expect(result.value.preferences).toEqual({ analysisCompleteEmail: true });
    expect(result.value.sessions.map((s) => [s.id, s.current])).toEqual([
      [user.sessionId, true],
      [other.id, false],
    ]);
    expect(result.value.sessions[0]?.device).toBe("Chrome 140 on Linux");
    expect(result.value.sessions[1]?.device).toBe("Firefox 141 on macOS");
    expect(result.value).toMatchObject({ hasPassword: false, providers: [], passkeys: [] });
    expect(JSON.stringify(result.value)).not.toContain(other.token);
  });

  it("turns analysis emails off and on, and rejects settings it does not offer", async () => {
    const user = await userActor(database());
    const off = await invoke(database().deps, accountPreferencesUpdate, user, {
      analysisCompleteEmail: false,
    });
    expect(off).toEqual({ ok: true, value: { analysisCompleteEmail: false } });
    const view = await invoke(database().deps, accountGet, user, {});
    expect(view.ok && view.value.preferences).toEqual({ analysisCompleteEmail: false });
    const on = await invoke(database().deps, accountPreferencesUpdate, user, {
      analysisCompleteEmail: true,
    });
    expect(on).toEqual({ ok: true, value: { analysisCompleteEmail: true } });
    const unknown = await invoke(database().deps, accountPreferencesUpdate, user, {
      analysisCompleteEmail: true,
      units: "imperial",
    });
    expect(unknown).toMatchObject({ ok: false, error: { kind: "Invalid" } });
  });

  it("revokes another session but refuses to revoke the current one", async () => {
    const user = await userActor(database());
    const other = await anotherSession(user.userId, FIREFOX_MAC);

    const self = await invoke(database().deps, accountSessionRevoke, user, {
      sessionId: user.sessionId,
    });
    expect(self).toMatchObject({ ok: false, error: { kind: "Conflict" } });

    const revoked = await invoke(database().deps, accountSessionRevoke, user, {
      sessionId: other.id,
    });
    expect(revoked).toEqual({ ok: true, value: { revoked: true } });
    const again = await invoke(database().deps, accountSessionRevoke, user, {
      sessionId: other.id,
    });
    expect(again).toMatchObject({ ok: false, error: { kind: "NotFound" } });
  });

  it("signs out everywhere else and keeps this session", async () => {
    const user = await userActor(database());
    await anotherSession(user.userId, FIREFOX_MAC);
    await anotherSession(user.userId, FIREFOX_MAC);

    const result = await invoke(database().deps, accountSessionsRevokeOthers, user, {});
    expect(result).toEqual({ ok: true, value: { revoked: 2 } });
    const view = await invoke(database().deps, accountGet, user, {});
    expect(view.ok && view.value.sessions.map((s) => s.id)).toEqual([user.sessionId]);
  });

  it("requires a signed-in user", async () => {
    const unauthenticated = { ok: false, error: { kind: "Unauthenticated" } };
    expect(await invoke(database().deps, accountGet, anonymous, {})).toMatchObject(unauthenticated);
    expect(await invoke(database().deps, accountSessionsRevokeOthers, anonymous, {})).toMatchObject(
      unauthenticated,
    );
  });

  it("describes devices from user agents and admits when it cannot", () => {
    expect(describeDevice(null)).toBeNull();
    expect(describeDevice("")).toBeNull();
    expect(describeDevice("curl/8.9.1")).toBeNull();
  });
});
