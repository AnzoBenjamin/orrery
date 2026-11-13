import { randomUUID } from "node:crypto";
import { emailSend, jobIdFor } from "@orrery/jobs";
import { describe, expect, it } from "vitest";
import { describeNetwork, deviceFamily, ipPrefix } from "../../src/server/devices.ts";
import { accountDeviceForget, accountGet } from "../../src/server/operations/account.ts";
import { invoke } from "../../src/server/operations/define.ts";
import { type NewSession, noteSignIn } from "../../src/server/sign-in-alerts.ts";
import { userActor, withTestDatabase } from "./support.ts";

const database = withTestDatabase();

const FIREFOX_LINUX = "Mozilla/5.0 (X11; Linux x86_64; rv:141.0) Gecko/20100101 Firefox/141.0";
const FIREFOX_LINUX_NEWER =
  "Mozilla/5.0 (X11; Linux x86_64; rv:142.0) Gecko/20100101 Firefox/142.0";
const SAFARI_IOS =
  "Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1";

const APP_URL = "https://orrery.example";

function signIn(userId: string, userAgent: string, ipAddress: string): Promise<[string, boolean]> {
  const session: NewSession = {
    id: randomUUID(),
    userId,
    userAgent,
    ipAddress,
    createdAt: new Date(),
  };
  return noteSignIn(
    { db: database().db, enqueue: database().deps.services.enqueue, appUrl: APP_URL },
    session,
  ).then((alerted) => [session.id, alerted]);
}

async function alertFor(sessionId: string) {
  const job = await database().boss.getJobById(
    emailSend.name,
    jobIdFor(emailSend.name, `sign-in-alert:${sessionId}`),
  );
  return job?.data as { payload: { message: Record<string, unknown> } } | undefined;
}

describe("new sign-in alerts", () => {
  it("stays quiet for the first sign-in, a repeat, and a browser update", async () => {
    const user = await userActor(database());
    for (const ua of [FIREFOX_LINUX, FIREFOX_LINUX, FIREFOX_LINUX_NEWER]) {
      const [sessionId, alerted] = await signIn(user.userId, ua, "203.0.113.7");
      expect(alerted).toBe(false);
      expect(await alertFor(sessionId)).toBeUndefined();
    }
    // Same browser, another address on the same network.
    expect((await signIn(user.userId, FIREFOX_LINUX, "203.0.42.1"))[1]).toBe(false);
  });

  it("emails the owner about a new device, then a new network", async () => {
    const user = await userActor(database());
    await signIn(user.userId, FIREFOX_LINUX, "203.0.113.7");

    const [phone, alerted] = await signIn(user.userId, SAFARI_IOS, "203.0.113.7");
    expect(alerted).toBe(true);
    const job = await alertFor(phone);
    expect(job?.payload.message).toMatchObject({
      template: "sign-in-alert",
      to: expect.stringContaining("@orrery.test"),
      device: "Safari on iOS",
      ipPrefix: "203.0.x.x",
      sessionsUrl: `${APP_URL}/account#sessions`,
    });
    expect(JSON.stringify(job)).not.toContain("203.0.113.7");

    const [travel, again] = await signIn(
      user.userId,
      FIREFOX_LINUX,
      "2001:db8:85a3::8a2e:370:7334",
    );
    expect(again).toBe(true);
    expect((await alertFor(travel))?.payload.message).toMatchObject({
      device: "Firefox on Linux",
      ipPrefix: "2001:db8:85a3::/48",
    });
  });

  it("lists known devices in account settings and alerts again once one is forgotten", async () => {
    const user = await userActor(database());
    const other = await userActor(database());
    await signIn(user.userId, FIREFOX_LINUX, "203.0.113.7");
    await signIn(user.userId, SAFARI_IOS, "198.51.100.4");

    const account = await invoke(database().deps, accountGet, user, {});
    if (!account.ok) throw new Error(account.error.message);
    expect(account.value.knownDevices.map((d) => [d.device, d.network])).toEqual([
      ["Safari on iOS", "198.51.x.x"],
      ["Firefox on Linux", "203.0.x.x"],
    ]);
    const phone = account.value.knownDevices[0];
    if (!phone) throw new Error("no device listed");

    // Another user cannot forget it.
    expect(
      await invoke(database().deps, accountDeviceForget, other, { deviceId: phone.id }),
    ).toMatchObject({ ok: false, error: { kind: "NotFound" } });
    expect(
      await invoke(database().deps, accountDeviceForget, user, { deviceId: phone.id }),
    ).toEqual({ ok: true, value: { forgotten: true } });
    expect((await signIn(user.userId, SAFARI_IOS, "198.51.100.4"))[1]).toBe(true);
  });
});

describe("device and network descriptions", () => {
  it("drops versions from the device and keeps only the network part of an address", () => {
    expect(deviceFamily(FIREFOX_LINUX)).toBe("Firefox on Linux");
    expect(deviceFamily(null)).toBe("Unknown browser");
    expect(deviceFamily("curl/8.9.1")).toBe("Unknown browser");
    expect(ipPrefix("203.0.113.7")).toBe("203.0");
    expect(ipPrefix("::ffff:203.0.113.7")).toBe("203.0");
    expect(ipPrefix("2001:0db8:85a3:0000:0000:8a2e:0370:7334")).toBe("2001:db8:85a3");
    expect(ipPrefix("2001:db8::1")).toBe("2001:db8:0");
    expect(ipPrefix("::1")).toBe("0:0:0");
    expect(ipPrefix("")).toBe("");
    expect(ipPrefix(null)).toBe("");
    expect(ipPrefix("not an address")).toBe("");
    expect(describeNetwork("203.0")).toBe("203.0.x.x");
    expect(describeNetwork("")).toBe("not recorded");
  });
});
