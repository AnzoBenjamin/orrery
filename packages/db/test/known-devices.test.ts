import { describe, expect, it } from "vitest";
import { forgetKnownDevice, listKnownDevices, newId, noteSignInDevice } from "../src/index.ts";
import { insertUser, useTestDatabase } from "./support.ts";

const database = useTestDatabase();

describe("known devices", () => {
  it("reports the first sign-in, a repeat, and a new device or network", async () => {
    const u = await insertUser(database(), "Ada");
    const laptop = { userId: u.id, device: "Firefox on Linux", ipPrefix: "203.0" };

    expect(await noteSignInDevice(database().db, laptop)).toMatchObject({
      isNew: true,
      hasOthers: false,
      name: "Ada",
      email: u.email,
    });
    expect(await noteSignInDevice(database().db, laptop)).toMatchObject({
      isNew: false,
      hasOthers: false,
    });
    expect(
      await noteSignInDevice(database().db, { ...laptop, device: "Safari on iOS" }),
    ).toMatchObject({ isNew: true, hasOthers: true });
    expect(await noteSignInDevice(database().db, { ...laptop, ipPrefix: "198.51" })).toMatchObject({
      isNew: true,
      hasOthers: true,
    });
    expect(await noteSignInDevice(database().db, laptop)).toMatchObject({
      isNew: false,
      hasOthers: true,
    });

    const devices = await listKnownDevices(database().db, u.id);
    expect(devices).toHaveLength(3);
    // The repeat moved the laptop to the front.
    expect(devices[0]).toMatchObject({ device: "Firefox on Linux", ipPrefix: "203.0" });
  });

  it("returns null for a user that does not exist", async () => {
    expect(
      await noteSignInDevice(database().db, { userId: newId(), device: "Chrome", ipPrefix: "" }),
    ).toBeNull();
  });

  it("forgets a device only for its owner", async () => {
    const owner = await insertUser(database());
    const other = await insertUser(database());
    await noteSignInDevice(database().db, {
      userId: owner.id,
      device: "Edge on Windows",
      ipPrefix: "",
    });
    const [device] = await listKnownDevices(database().db, owner.id);
    if (!device) throw new Error("device was not recorded");

    expect(await forgetKnownDevice(database().db, other.id, device.id)).toBe(false);
    expect(await listKnownDevices(database().db, owner.id)).toHaveLength(1);
    expect(await forgetKnownDevice(database().db, owner.id, device.id)).toBe(true);
    expect(await listKnownDevices(database().db, owner.id)).toEqual([]);
    expect(await listKnownDevices(database().db, other.id)).toEqual([]);
  });
});
