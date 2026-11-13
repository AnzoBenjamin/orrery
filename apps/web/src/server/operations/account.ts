import {
  forgetKnownDevice,
  getUserPreferences,
  type KnownDeviceRecord,
  listActiveSessions,
  listKnownDevices,
  listLinkedAccounts,
  listPasskeys,
  revokeOtherUserSessions,
  revokeUserSession,
  type SessionRecord,
  type UserPreferences,
  updateUserPreferences,
} from "@orrery/db";
import { z } from "zod";
import { describeDevice, describeNetwork } from "../devices.ts";
import { DomainError, notFound } from "../domain-errors.ts";
import { requireUser } from "../policy.ts";
import { defineOperation } from "./define.ts";

// Account settings (requirements 4.7 and 10.3). Reads come from the Better Auth tables through
// query modules that never return secrets. Changes Better Auth owns end to end (linking and
// unlinking providers, passkeys, account deletion) go through the Better Auth client instead.

/**
 * Preferences shown in account settings. Sound and display units join when the workbench
 * features they control exist, so no setting appears before it has an effect.
 */
export interface PreferencesView {
  analysisCompleteEmail: boolean;
}

export interface SessionView {
  id: string;
  /** True for the session this request came in on. */
  current: boolean;
  /** Browser and operating system, such as "Firefox 141 on macOS", or null when unknown. */
  device: string | null;
  ipAddress: string | null;
  signedInAt: string;
  lastActiveAt: string;
}

export interface PasskeyView {
  id: string;
  name: string | null;
  synced: boolean;
  createdAt: string | null;
}

export interface KnownDeviceView {
  id: string;
  /** Browser and operating system without versions, such as "Firefox on Linux". */
  device: string;
  /** The network as shown after "Network": "203.0.x.x", or "not recorded". */
  network: string;
  firstSeenAt: string;
  lastSeenAt: string;
}

export interface AccountView {
  preferences: PreferencesView;
  sessions: SessionView[];
  /** Whether the account has an email and password sign-in. */
  hasPassword: boolean;
  /** Linked OAuth providers (`github`, `google`): the account record id and when it was linked. */
  providers: { id: string; providerId: string; linkedAt: string }[];
  passkeys: PasskeyView[];
  /** Devices and networks signed in from; a sign-in from any other sends an alert. */
  knownDevices: KnownDeviceView[];
}

function sessionView(s: SessionRecord, currentId: string): SessionView {
  return {
    id: s.id,
    current: s.id === currentId,
    device: describeDevice(s.userAgent),
    ipAddress: s.ipAddress,
    signedInAt: s.createdAt.toISOString(),
    lastActiveAt: s.updatedAt.toISOString(),
  };
}

function knownDeviceView(d: KnownDeviceRecord): KnownDeviceView {
  return {
    id: d.id,
    device: d.device,
    network: describeNetwork(d.ipPrefix),
    firstSeenAt: d.firstSeenAt.toISOString(),
    lastSeenAt: d.lastSeenAt.toISOString(),
  };
}

function preferencesView(p: UserPreferences): PreferencesView {
  return { analysisCompleteEmail: p.analysisCompleteEmail };
}

export const accountGet = defineOperation({
  name: "account.get",
  input: z.object({}),
  run: async ({ actor, tx }): Promise<AccountView> => {
    const user = requireUser(actor);
    // One transaction is one connection, so the reads run in sequence.
    const preferences = await getUserPreferences(tx, user.userId);
    const sessions = await listActiveSessions(tx, user.userId);
    const accounts = await listLinkedAccounts(tx, user.userId);
    const passkeys = await listPasskeys(tx, user.userId);
    const knownDevices = await listKnownDevices(tx, user.userId);
    return {
      preferences: preferencesView(preferences),
      // The current session first, then the most recently active.
      sessions: sessions
        .map((s) => sessionView(s, user.sessionId))
        .sort((a, b) => Number(b.current) - Number(a.current)),
      hasPassword: accounts.some((a) => a.providerId === "credential"),
      providers: accounts
        .filter((a) => a.providerId !== "credential")
        .map((a) => ({ id: a.id, providerId: a.providerId, linkedAt: a.createdAt.toISOString() })),
      passkeys: passkeys.map((p) => ({
        id: p.id,
        name: p.name,
        synced: p.backedUp,
        createdAt: p.createdAt?.toISOString() ?? null,
      })),
      knownDevices: knownDevices.map(knownDeviceView),
    };
  },
});

export const accountPreferencesUpdate = defineOperation({
  name: "account.preferences.update",
  input: z.object({ analysisCompleteEmail: z.boolean() }),
  run: async ({ actor, input, tx }): Promise<PreferencesView> => {
    const user = requireUser(actor);
    const updated = await updateUserPreferences(tx, user.userId, {
      analysisCompleteEmail: input.analysisCompleteEmail,
    });
    return preferencesView(updated);
  },
});

export const accountSessionRevoke = defineOperation({
  name: "account.session.revoke",
  input: z.object({ sessionId: z.uuid("That session does not exist.") }),
  run: async ({ actor, input, tx }) => {
    const user = requireUser(actor);
    if (input.sessionId === user.sessionId) {
      throw new DomainError(
        "Conflict",
        "That is the session you are using now. Sign out to end it.",
      );
    }
    if (!(await revokeUserSession(tx, user.userId, input.sessionId))) {
      throw notFound("That session");
    }
    return { revoked: true as const };
  },
});

export const accountSessionsRevokeOthers = defineOperation({
  name: "account.sessions.revoke-others",
  input: z.object({}),
  run: async ({ actor, tx }) => {
    const user = requireUser(actor);
    return { revoked: await revokeOtherUserSessions(tx, user.userId, user.sessionId) };
  },
});

/** Forgets a device, so the next sign-in from it sends the new sign-in alert again. */
export const accountDeviceForget = defineOperation({
  name: "account.device.forget",
  input: z.object({ deviceId: z.uuid("That device does not exist.") }),
  run: async ({ actor, input, tx }) => {
    const user = requireUser(actor);
    if (!(await forgetKnownDevice(tx, user.userId, input.deviceId))) {
      throw notFound("That device");
    }
    return { forgotten: true as const };
  },
});
