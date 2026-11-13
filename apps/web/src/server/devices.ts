import { isIPv4, isIPv6 } from "node:net";
import { parse as parseUserAgent } from "bowser";

function browserAndOs(userAgent: string | null, withVersion: boolean): string | null {
  if (!userAgent) return null;
  const parsed = parseUserAgent(userAgent);
  const major = withVersion ? parsed.browser.version?.split(".")[0] : undefined;
  const browser = parsed.browser.name ? [parsed.browser.name, major].filter(Boolean).join(" ") : "";
  const os = parsed.os.name ?? "";
  if (browser && os) return `${browser} on ${os}`;
  return browser || os || null;
}

/** "Chrome 140 on Linux" from a user agent string; null when nothing useful can be read. */
export function describeDevice(userAgent: string | null): string | null {
  return browserAndOs(userAgent, true);
}

/**
 * "Chrome on Linux": the device as the sign-in alert compares it. Versions are left out so a
 * browser update does not look like a new device.
 */
export function deviceFamily(userAgent: string | null): string {
  return browserAndOs(userAgent, false) ?? "Unknown browser";
}

/**
 * The network part of an address, never the full address: the first two octets of IPv4
 * ("203.0") or the first three hextets of IPv6 ("2001:db8:85a3"). IPv4-mapped IPv6 is treated as
 * IPv4. Empty when the address is missing or unreadable.
 */
export function ipPrefix(address: string | null | undefined): string {
  const value = address?.trim() ?? "";
  const mapped = /^::ffff:(\d+\.\d+\.\d+\.\d+)$/i.exec(value)?.[1];
  const v4 = mapped ?? value;
  if (isIPv4(v4)) return v4.split(".").slice(0, 2).join(".");
  if (!isIPv6(value)) return "";
  // Expand "::" so the first three groups are the real leading hextets.
  const [head = "", tail = ""] = value.split("::");
  const headGroups = head ? head.split(":") : [];
  const tailGroups = tail ? tail.split(":") : [];
  const groups = value.includes("::")
    ? [...headGroups, ...Array(8 - headGroups.length - tailGroups.length).fill("0"), ...tailGroups]
    : headGroups;
  return groups
    .slice(0, 3)
    .map((g) => g.toLowerCase().replace(/^0+(?=.)/, ""))
    .join(":");
}

/** How the alert and account settings show a prefix, after the word "Network". */
export function describeNetwork(prefix: string): string {
  if (prefix === "") return "not recorded";
  return prefix.includes(":") ? `${prefix}::/48` : `${prefix}.x.x`;
}
