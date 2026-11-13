import type { Result } from "../server/domain-errors.ts";

/** Field errors from an Invalid result, in the shape React Aria forms accept. */
export function fieldErrors(result: Result<unknown>): Record<string, string> {
  return !result.ok && result.error.kind === "Invalid" ? (result.error.fields ?? {}) : {};
}

/** The banner text for a failed result, including the support reference when there is one. */
export function failureMessage(result: Result<unknown>): string | null {
  if (result.ok) return null;
  const { message, reference } = result.error;
  return reference ? `${message} (reference ${reference})` : message;
}
