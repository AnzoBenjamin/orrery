import { randomBytes } from "node:crypto";
import { schema } from "@orrery/db";
import { eq } from "drizzle-orm";
import fc from "fast-check";
import { describe, expect, it } from "vitest";
import type { Actor } from "../../src/server/actor.ts";
import { type AnyOperation, invoke } from "../../src/server/operations/define.ts";
import { footageUploadCreate } from "../../src/server/operations/footage.ts";
import { operations } from "../../src/server/operations/registry.ts";
import { shareCreate } from "../../src/server/operations/shares.ts";
import { userActor, withTestDatabase } from "./support.ts";

/**
 * Correctness property 1 (platform-foundation design): for any two users A and B and any
 * operation, a call by B referencing A's resource returns NotFound and changes no rows.
 * Validates requirements 5.2 and 5.4.
 */

const database = withTestDatabase();

interface Fixture {
  /** A's share link for the specimen. */
  shareLinkId: string;
  userId: string;
  sessionId: string;
  specimenId: string;
  /** A's footage with an open upload. */
  footageId: string;
}

/** How B attacks A's data through each operation. Operations without a resource get "own". */
type Case =
  | { kind: "resource"; input: (a: Fixture, text: string) => Record<string, unknown> }
  | {
      kind: "own";
      input?: (text: string) => Record<string, unknown>;
      check: (result: unknown, a: Fixture) => void;
    };

/** B's own results never mention any of A's identifiers. */
const leaksNothingOf = (result: unknown, a: Fixture) => {
  const json = JSON.stringify(result);
  for (const id of [a.userId, a.sessionId, a.specimenId, a.footageId, a.shareLinkId]) {
    expect(json).not.toContain(id);
  }
};

const cases: Record<string, Case> = {
  "specimen.create": {
    kind: "own",
    input: (text) => ({ title: `B ${text}`.trim() || "B" }),
    check: leaksNothingOf,
  },
  "specimen.list": { kind: "own", check: leaksNothingOf },
  "specimen.get": { kind: "resource", input: (a) => ({ specimenId: a.specimenId }) },
  "specimen.update": {
    kind: "resource",
    input: (a, text) => ({ specimenId: a.specimenId, title: text, description: text }),
  },
  "specimen.delete": { kind: "resource", input: (a) => ({ specimenId: a.specimenId }) },
  "account.get": { kind: "own", check: leaksNothingOf },
  "account.preferences.update": {
    kind: "own",
    input: (text) => ({ analysisCompleteEmail: text.length % 2 === 0 }),
    check: leaksNothingOf,
  },
  "account.session.revoke": { kind: "resource", input: (a) => ({ sessionId: a.sessionId }) },
  "account.sessions.revoke-others": { kind: "own", check: leaksNothingOf },
  "footage.list": { kind: "resource", input: (a) => ({ specimenId: a.specimenId }) },
  "footage.usage": { kind: "own", check: leaksNothingOf },
  "footage.upload.create": {
    kind: "resource",
    input: (a, text) => ({
      specimenId: a.specimenId,
      role: "broken",
      filename: `${text}.mp4`,
      byteSize: 10,
    }),
  },
  "footage.upload.sign": {
    kind: "resource",
    input: (a, text) => ({
      footageId: a.footageId,
      request: text.length % 2 === 0 ? { step: "create" } : { step: "abort", uploadId: text },
    }),
  },
  "footage.upload.complete": { kind: "resource", input: (a) => ({ footageId: a.footageId }) },
  "footage.upload.abort": { kind: "resource", input: (a) => ({ footageId: a.footageId }) },
  "footage.delete": { kind: "resource", input: (a) => ({ footageId: a.footageId }) },
  "footage.playback": { kind: "resource", input: (a) => ({ footageId: a.footageId }) },
  "share.list": { kind: "resource", input: (a) => ({ specimenId: a.specimenId }) },
  "share.create": { kind: "resource", input: (a) => ({ specimenId: a.specimenId }) },
  "share.revoke": { kind: "resource", input: (a) => ({ shareLinkId: a.shareLinkId }) },
  // A share link is the only grant; without A's token B gets nothing.
  "share.open": { kind: "resource", input: () => ({ token: randomToken() }) },
  "share.playback": {
    kind: "resource",
    input: (a) => ({ token: randomToken(), footageId: a.footageId }),
  },
};

function randomToken() {
  return randomBytes(32).toString("base64url");
}

async function snapshotOf(fixture: Fixture) {
  const db = database().db;
  const specimens = await db.select().from(schema.specimen);
  const deletions = await db.select().from(schema.objectDeletion);
  const sessions = await db
    .select()
    .from(schema.session)
    .where(eq(schema.session.userId, fixture.userId));
  const preferences = await db
    .select()
    .from(schema.userPreference)
    .where(eq(schema.userPreference.userId, fixture.userId));
  const footage = await db
    .select()
    .from(schema.footage)
    .where(eq(schema.footage.specimenId, fixture.specimenId));
  const uploads = await db.select().from(schema.uploadSession);
  const shares = (await db.select().from(schema.shareLink)).map(({ lastUsedAt: _, ...l }) => l);
  const parts = (await database().storage.listMultipartUploads(`users/${fixture.userId}/`)).map(
    (u) => u.uploadId,
  );
  return JSON.stringify({
    a: specimens.find((s) => s.id === fixture.specimenId),
    footage,
    uploads,
    shares,
    parts,
    deletions,
    sessions,
    preferences,
  });
}

describe("cross-user authorization", () => {
  it("has a case for every registered operation", () => {
    expect(operations.map((o) => o.name).sort()).toEqual(Object.keys(cases).sort());
  });

  it.each(operations.map((op) => [op.name, op] as [string, AnyOperation]))(
    "%s never exposes or changes another user's data",
    async (name, op) => {
      const testCase = cases[name];
      if (!testCase) throw new Error(`no cross-user case for ${name}`);
      const a = await userActor(database());
      const b: Actor = await userActor(database());
      const created = await invoke(database().deps, operations[0] as AnyOperation, a, {
        title: "A's private specimen",
      });
      if (!created.ok) throw new Error("fixture creation failed");
      const specimenId = (created.value as { id: string }).id;
      const upload = await invoke(database().deps, footageUploadCreate, a, {
        specimenId,
        role: "reference",
        filename: "a.mp4",
        byteSize: 1000,
      });
      if (!upload.ok) throw new Error(`fixture upload failed: ${upload.error.message}`);
      const share = await invoke(database().deps, shareCreate, a, { specimenId });
      if (!share.ok) throw new Error(`fixture share failed: ${share.error.message}`);
      const fixture: Fixture = {
        shareLinkId: share.value.link.id,
        userId: a.userId,
        sessionId: a.sessionId,
        specimenId,
        footageId: upload.value.footageId,
      };

      await fc.assert(
        fc.asyncProperty(fc.string({ minLength: 1, maxLength: 40 }), async (text) => {
          const before = await snapshotOf(fixture);
          if (testCase.kind === "resource") {
            const result = await invoke(database().deps, op, b, testCase.input(fixture, text));
            expect(result).toMatchObject({ ok: false, error: { kind: "NotFound" } });
          } else {
            const input = testCase.input?.(text) ?? {};
            testCase.check(await invoke(database().deps, op, b, input), fixture);
          }
          expect(await snapshotOf(fixture)).toBe(before);
        }),
        { numRuns: 12 },
      );
    },
  );
});
