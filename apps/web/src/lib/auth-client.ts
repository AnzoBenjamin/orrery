import { passkeyClient } from "@better-auth/passkey/client";
import { createAuthClient } from "better-auth/react";

/** Browser client for Better Auth. Same origin, so no base URL is needed. */
export const authClient = createAuthClient({ plugins: [passkeyClient()] });

/** User-facing text for Better Auth error codes: what happened and what to do next. */
export function authErrorMessage(error: { code?: string | undefined; status?: number }): string {
  switch (error.code) {
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
    default:
      if (error.status === 429) {
        return "Too many attempts from this network. Wait a few minutes, then try again.";
      }
      return "Something went wrong on our side. Try again in a moment.";
  }
}
