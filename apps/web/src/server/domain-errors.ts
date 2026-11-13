/**
 * Domain errors (design: "Error handling"). Server functions return these as values, never as
 * thrown errors, so every failure reaches the UI as a typed state with a readable message.
 */
export type DomainErrorKind =
  | "NotFound"
  | "Forbidden"
  | "Conflict"
  | "Invalid"
  | "RateLimited"
  | "Unavailable"
  | "Unauthenticated";

export class DomainError extends Error {
  readonly kind: DomainErrorKind;
  /** Per-field messages for Invalid, keyed by input path ("title", "description"). */
  readonly fields: Readonly<Record<string, string>> | undefined;

  constructor(kind: DomainErrorKind, message: string, fields?: Record<string, string>) {
    super(message);
    this.name = "DomainError";
    this.kind = kind;
    this.fields = fields;
  }
}

/** Not authorized and not found are indistinguishable to the caller (requirement 5.2). */
export const notFound = (what = "That item") =>
  new DomainError("NotFound", `${what} does not exist, or you do not have access to it.`);

export type Result<T> =
  | { ok: true; value: T }
  | {
      ok: false;
      error: {
        kind: DomainErrorKind;
        message: string;
        fields?: Record<string, string> | undefined;
        reference?: string | undefined;
      };
    };
