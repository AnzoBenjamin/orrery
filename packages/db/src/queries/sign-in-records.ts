import { and, asc, desc, eq, gt, ne, sql } from "drizzle-orm";
import type { Executor } from "../client.ts";
import { account, passkey, session } from "../schema/index.ts";

// Read and revoke views of the Better Auth tables for account settings. Each function is scoped
// to one user, and none returns a secret: no session tokens, OAuth tokens, password hashes, or
// passkey public keys leave this module.

export interface SessionRecord {
  id: string;
  createdAt: Date;
  updatedAt: Date;
  expiresAt: Date;
  ipAddress: string | null;
  userAgent: string | null;
}

/** The user's unexpired sessions, most recently active first. */
export async function listActiveSessions(ex: Executor, userId: string): Promise<SessionRecord[]> {
  return ex
    .select({
      id: session.id,
      createdAt: session.createdAt,
      updatedAt: session.updatedAt,
      expiresAt: session.expiresAt,
      ipAddress: session.ipAddress,
      userAgent: session.userAgent,
    })
    .from(session)
    .where(and(eq(session.userId, userId), gt(session.expiresAt, sql`now()`)))
    .orderBy(desc(session.updatedAt), desc(session.id));
}

/** Ends one of the user's sessions. Returns false when the user has no session with that id. */
export async function revokeUserSession(
  ex: Executor,
  userId: string,
  sessionId: string,
): Promise<boolean> {
  const rows = await ex
    .delete(session)
    .where(and(eq(session.id, sessionId), eq(session.userId, userId)))
    .returning({ id: session.id });
  return rows.length > 0;
}

/** Ends every session of the user except `keepSessionId`. Returns how many were ended. */
export async function revokeOtherUserSessions(
  ex: Executor,
  userId: string,
  keepSessionId: string,
): Promise<number> {
  const rows = await ex
    .delete(session)
    .where(and(eq(session.userId, userId), ne(session.id, keepSessionId)))
    .returning({ id: session.id });
  return rows.length;
}

export interface LinkedAccountRecord {
  id: string;
  /** `credential` for email and password, otherwise the OAuth provider (`github`, `google`). */
  providerId: string;
  createdAt: Date;
}

export async function listLinkedAccounts(
  ex: Executor,
  userId: string,
): Promise<LinkedAccountRecord[]> {
  return ex
    .select({ id: account.id, providerId: account.providerId, createdAt: account.createdAt })
    .from(account)
    .where(eq(account.userId, userId))
    .orderBy(asc(account.id));
}

export interface PasskeyRecord {
  id: string;
  name: string | null;
  /** `singleDevice` or `multiDevice` (synced, such as through a platform keychain). */
  deviceType: string;
  backedUp: boolean;
  createdAt: Date | null;
}

export async function listPasskeys(ex: Executor, userId: string): Promise<PasskeyRecord[]> {
  return ex
    .select({
      id: passkey.id,
      name: passkey.name,
      deviceType: passkey.deviceType,
      backedUp: passkey.backedUp,
      createdAt: passkey.createdAt,
    })
    .from(passkey)
    .where(eq(passkey.userId, userId))
    .orderBy(asc(passkey.id));
}
