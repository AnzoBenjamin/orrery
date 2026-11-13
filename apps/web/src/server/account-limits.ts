import { createHash } from "node:crypto";
import { DomainError } from "./domain-errors.ts";
import type { Limit, LimitName } from "./rate-limits.ts";

/** Better Auth endpoints that act on the account named by the `email` in their body. */
const accountLimitedPaths: Record<string, LimitName> = {
  "/sign-in/email": "sign-in-account",
  "/sign-up/email": "sign-up-account",
  "/request-password-reset": "password-reset-account",
  "/send-verification-email": "verification-email-account",
};

/** Addresses are compared as Better Auth stores them: trimmed and lower-cased. */
function accountKey(email: string): string {
  return createHash("sha256").update(email.trim().toLowerCase()).digest("hex");
}

/** The per-account limit a request counts against, or null when it has none. */
export function accountLimitFor(
  path: string,
  body: unknown,
): { name: LimitName; key: string } | null {
  const name = accountLimitedPaths[path];
  if (!name || typeof body !== "object" || body === null || !("email" in body)) return null;
  const { email } = body;
  if (typeof email !== "string" || email.trim() === "") return null;
  return { name, key: accountKey(email) };
}

/** Error code the browser maps to its message (lib/auth-client.ts). */
export const ACCOUNT_RATE_LIMITED = "ACCOUNT_RATE_LIMITED";

/**
 * Counts one request against its account's limit. Returns the user-facing message when the
 * limit is used up, or null when the request may go ahead.
 */
export async function checkAccountLimit(
  limit: Limit,
  path: string,
  body: unknown,
): Promise<string | null> {
  const applies = accountLimitFor(path, body);
  if (!applies) return null;
  try {
    await limit(applies.name, applies.key);
    return null;
  } catch (error) {
    if (error instanceof DomainError && error.kind === "RateLimited") return error.message;
    throw error;
  }
}
