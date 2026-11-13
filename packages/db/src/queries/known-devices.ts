import { and, desc, eq, ne, sql } from "drizzle-orm";
import type { Executor } from "../client.ts";
import { knownDevice, user } from "../schema/index.ts";

export interface KnownDeviceRecord {
  id: string;
  device: string;
  ipPrefix: string;
  firstSeenAt: Date;
  lastSeenAt: Date;
}

export interface SignInNoted {
  /** True when this device and network had not been seen for the user before. */
  isNew: boolean;
  /** True when the user had signed in from some other device or network before this one. */
  hasOthers: boolean;
  /** The user's name and address, for the alert. */
  name: string;
  email: string;
}

/**
 * Records a sign-in from `device` on `ipPrefix`, creating the row the first time and moving its
 * last-seen time after that. Returns null when the user does not exist.
 */
export async function noteSignInDevice(
  ex: Executor,
  input: { userId: string; device: string; ipPrefix: string },
): Promise<SignInNoted | null> {
  const [owner] = await ex
    .select({ name: user.name, email: user.email })
    .from(user)
    .where(eq(user.id, input.userId));
  if (!owner) return null;
  const [row] = await ex
    .insert(knownDevice)
    .values(input)
    .onConflictDoUpdate({
      target: [knownDevice.userId, knownDevice.device, knownDevice.ipPrefix],
      set: { lastSeenAt: sql`now()` },
    })
    // xmax is 0 only for a row this statement inserted.
    .returning({ id: knownDevice.id, inserted: sql<boolean>`xmax = 0` });
  if (!row) throw new Error("known device upsert returned no row");
  const [other] = await ex
    .select({ id: knownDevice.id })
    .from(knownDevice)
    .where(and(eq(knownDevice.userId, input.userId), ne(knownDevice.id, row.id)))
    .limit(1);
  return { isNew: row.inserted, hasOthers: other !== undefined, ...owner };
}

/** The user's known devices, most recently seen first. */
export async function listKnownDevices(ex: Executor, userId: string): Promise<KnownDeviceRecord[]> {
  return ex
    .select({
      id: knownDevice.id,
      device: knownDevice.device,
      ipPrefix: knownDevice.ipPrefix,
      firstSeenAt: knownDevice.firstSeenAt,
      lastSeenAt: knownDevice.lastSeenAt,
    })
    .from(knownDevice)
    .where(eq(knownDevice.userId, userId))
    .orderBy(desc(knownDevice.lastSeenAt), desc(knownDevice.id));
}

/**
 * Forgets one of the user's known devices, so the next sign-in from it sends an alert. Returns
 * false when the user has no such device.
 */
export async function forgetKnownDevice(
  ex: Executor,
  userId: string,
  deviceId: string,
): Promise<boolean> {
  const rows = await ex
    .delete(knownDevice)
    .where(and(eq(knownDevice.id, deviceId), eq(knownDevice.userId, userId)))
    .returning({ id: knownDevice.id });
  return rows.length > 0;
}
