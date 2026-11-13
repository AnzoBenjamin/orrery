import { passkeyClient } from "@better-auth/passkey/client";
import { createAuthClient } from "better-auth/react";

/** Browser client for Better Auth. Same origin, so no base URL is needed. */
export const authClient = createAuthClient({ plugins: [passkeyClient()] });

/** User-facing text for Better Auth error codes: what happened and what to do next. */
export function authErrorMessage(error: {
  code?: string | undefined;
  status?: number;
  message?: string | undefined;
}): string {
  switch (error.code) {
    case "ACCOUNT_RATE_LIMITED":
      // The server's message says how long to wait (server/account-limits.ts).
      return error.message ?? "Too many attempts for this account. Wait a while, then try again.";
    case "INVALID_EMAIL_OR_PASSWORD":
      return "That email and password do not match an account. Check both, or reset your password.";
    case "EMAIL_NOT_VERIFIED":
      return "Confirm your email address first. We have sent a new confirmation link.";
    case "USER_ALREADY_EXISTS":
    case "USER_ALREADY_EXISTS_USE_ANOTHER_EMAIL":
      return "An account with that email already exists. Sign in instead, or reset its password.";
    case "PASSWORD_TOO_SHORT":
      return "Use at least 10 characters for your password.";
    case "PASSWORD_TOO_LONG":
      return "Use at most 128 characters for your password.";
    case "INVALID_TOKEN":
      return "This link is invalid or has expired. Request a new one.";
    case "INVALID_PASSWORD":
      return "That password is not correct. Enter the password you sign in with.";
    case "SESSION_EXPIRED":
    case "SESSION_NOT_FRESH":
      return "For your safety, this needs a recent sign-in. Sign out, sign in again, then retry.";
    case "FAILED_TO_UNLINK_LAST_ACCOUNT":
      return "This is your only way to sign in. Add another before removing it.";
    case "PASSKEY_NOT_FOUND":
      return "That passkey no longer exists. Reload the page to see your current passkeys.";
    case "AUTH_CANCELLED":
    case "ERROR_CEREMONY_ABORTED":
      return "The passkey request was cancelled. Try again when your device asks.";
    case "ERROR_AUTHENTICATOR_PREVIOUSLY_REGISTERED":
      return "This device already holds a passkey for your account. Use that one to sign in.";
    default:
      if (error.status === 429) {
        return "Too many attempts from this network. Wait a few minutes, then try again.";
      }
      return "Something went wrong on our side. Try again in a moment.";
  }
}
