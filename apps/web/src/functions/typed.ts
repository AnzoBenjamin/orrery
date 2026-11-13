import type { z } from "zod";

/**
 * The validator for a server function's transport. It only types the input for callers: each
 * operation's strict schema validates it inside `call`, where a rejection becomes an Invalid
 * result with per-field messages.
 */
export const typed =
  <S extends z.ZodObject>(_schema: S) =>
  (input: z.input<S>) =>
    input;
