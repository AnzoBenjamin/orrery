import { randomBytes } from "node:crypto";
import { describe, expect, it } from "vitest";
import {
  listActiveSessions,
  listLinkedAccounts,
  listPasskeys,
  newId,
  revokeOtherUserSessions,
  revokeUserSession,
} from "../src/index.ts";
import { account, passkey, session } from "../src/schema/index.ts";
import type { TestDatabase } from "../src/testing/index.ts";
import { insertUser, useTestDatabase } from "./support.ts";

const database = useTestDatabase();

const HOUR_MS = 3_600_000;

async function insertSession(db: TestDatabase, userId: string, expiresInMs = HOUR_MS) {
  const [row] = await db.db
    .insert(session)
    .values({
      userId,
      token: randomBytes(24).toString("hex"),
      expiresAt: new Date(Date.now() + expiresInMs),
      updatedAt: new Date(),
      ipAddress: "203.0.113.7",
      userAgent: "Mozilla/5.0 (X11; Linux x86_64) Chrome/140.0 Safari/537.36",
    })
    .returning();
  if (!row) throw new Error("session insert returned no row");
  return row;
}

describe("sign-in records", () => {
  it("lists only the user's unexpired sessions and never their tokens", async () => {
    const u = await insertUser(database());
    const other = await insertUser(database());
    const live = await insertSession(database(), u.id);
    await insertSession(database(), u.id, -HOUR_MS);
    await insertSession(database(), other.id);

    const sessions = await listActiveSessions(database().db, u.id);
    expect(sessions.map((s) => s.id)).toEqual([live.id]);
    expect(JSON.stringify(sessions)).not.toContain(live.token);
    expect(sessions[0]).toMatchObject({ ipAddress: "203.0.113.7" });
  });

  it("revokes a session only for its owner", async () => {
    const u = await insertUser(database());
    const other = await insertUser(database());
    const s = await insertSession(database(), u.id);

    expect(await revokeUserSession(database().db, other.id, s.id)).toBe(false);
    expect(await listActiveSessions(database().db, u.id)).toHaveLength(1);
    expect(await revokeUserSession(database().db, u.id, s.id)).toBe(true);
    expect(await listActiveSessions(database().db, u.id)).toHaveLength(0);
    expect(await revokeUserSession(database().db, u.id, newId())).toBe(false);
  });

  it("revokes every other session and keeps the current one and other users' sessions", async () => {
    const u = await insertUser(database());
    const other = await insertUser(database());
    const current = await insertSession(database(), u.id);
    await insertSession(database(), u.id);
    await insertSession(database(), u.id);
    const bystander = await insertSession(database(), other.id);

    expect(await revokeOtherUserSessions(database().db, u.id, current.id)).toBe(2);
    expect((await listActiveSessions(database().db, u.id)).map((s) => s.id)).toEqual([current.id]);
    expect((await listActiveSessions(database().db, other.id)).map((s) => s.id)).toEqual([
      bystander.id,
    ]);
  });

  it("lists linked accounts and passkeys without secrets", async () => {
    const u = await insertUser(database());
    await database()
      .db.insert(account)
      .values([
        {
          userId: u.id,
          accountId: u.id,
          providerId: "credential",
          password: "scrypt-hash-not-for-display",
          updatedAt: new Date(),
        },
        {
          userId: u.id,
          accountId: "gh-123",
          providerId: "github",
          accessToken: "gho_secret",
          updatedAt: new Date(),
        },
      ]);
    await database().db.insert(passkey).values({
      userId: u.id,
      name: "Workshop laptop",
      publicKey: "public-key-material",
      credentialID: "cred-1",
      counter: 0,
      deviceType: "multiDevice",
      backedUp: true,
      createdAt: new Date(),
    });

    const accounts = await listLinkedAccounts(database().db, u.id);
    expect(accounts.map((a) => a.providerId)).toEqual(["credential", "github"]);
    expect(JSON.stringify(accounts)).not.toMatch(/scrypt|gho_secret/);

    const passkeys = await listPasskeys(database().db, u.id);
    expect(passkeys).toMatchObject([{ name: "Workshop laptop", backedUp: true }]);
    expect(JSON.stringify(passkeys)).not.toContain("public-key-material");
  });
});
