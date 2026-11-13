import { type Db, noteSignInDevice } from "@orrery/db";
import { emailSend } from "@orrery/jobs";
import { describeNetwork, deviceFamily, ipPrefix } from "./devices.ts";
import type { Services } from "./operations/define.ts";

export interface NewSession {
  id: string;
  userId: string;
  userAgent?: string | null | undefined;
  ipAddress?: string | null | undefined;
  createdAt: Date;
}

/**
 * Called for every new session (Better Auth's session.create.after hook). Records the device
 * and network, and queues the new sign-in alert (requirement 10.2) when that pair is new and the
 * account has signed in from somewhere else before. The first sign-in after sign-up sends
 * nothing. Returns whether an alert was queued.
 */
export async function noteSignIn(
  deps: { db: Db; enqueue: Services["enqueue"]; appUrl: string },
  session: NewSession,
): Promise<boolean> {
  const device = deviceFamily(session.userAgent ?? null);
  const prefix = ipPrefix(session.ipAddress);
  const noted = await deps.db.transaction((tx) =>
    noteSignInDevice(tx, { userId: session.userId, device, ipPrefix: prefix }),
  );
  if (!noted?.isNew || !noted.hasOthers) return false;
  // Queued after the device is recorded, the same order as other jobs (the queue has its own
  // connection). One alert per session, however often the hook runs.
  await deps.enqueue(emailSend, {
    message: {
      template: "sign-in-alert",
      to: noted.email,
      name: noted.name,
      at: session.createdAt.toISOString(),
      device,
      ipPrefix: describeNetwork(prefix),
      sessionsUrl: new URL("/account#sessions", deps.appUrl).toString(),
    },
    idempotencyKey: `sign-in-alert:${session.id}`,
  });
  return true;
}
