import type { Db, Executor } from "@orrery/db";
import type { z } from "zod";
import type { Actor } from "../actor.ts";
import { DomainError, type Result } from "../domain-errors.ts";

export interface OperationContext<TInput> {
  actor: Actor;
  input: TInput;
  /** An open transaction; the operation commits only if `run` resolves. */
  tx: Executor;
}

/**
 * An application operation behind one server function. Inputs are strict objects, so unknown
 * fields are rejected (requirement 12.2). `run` receives the actor and must authorize through
 * policy.ts; the cross-user test enumerates every operation in the registry to prove it does.
 */
export interface Operation<TSchema extends z.ZodObject, TOutput> {
  readonly name: string;
  readonly input: TSchema;
  readonly run: (ctx: OperationContext<z.output<TSchema>>) => Promise<TOutput>;
}

export function defineOperation<TSchema extends z.ZodObject, TOutput>(
  op: Operation<TSchema, TOutput>,
): Operation<TSchema, TOutput> {
  return { ...op, input: op.input.strict() as TSchema };
}

// biome-ignore lint/suspicious/noExplicitAny: a registry holds operations of every input and output type.
export type AnyOperation = Operation<z.ZodObject, any>;

export interface InvokeOptions {
  /** Called with unexpected errors so they reach GlitchTip; returns a reference for the user. */
  report?: (error: unknown) => string;
}

/** Validates input, runs the operation in a transaction, and maps errors to a Result. */
export async function invoke<TSchema extends z.ZodObject, TOutput>(
  db: Db,
  op: Operation<TSchema, TOutput>,
  actor: Actor,
  rawInput: unknown,
  options: InvokeOptions = {},
): Promise<Result<TOutput>> {
  const parsed = op.input.safeParse(rawInput);
  if (!parsed.success) {
    const fields: Record<string, string> = {};
    for (const issue of parsed.error.issues) {
      const key = issue.path.join(".") || "(input)";
      fields[key] ??= issue.message;
    }
    return {
      ok: false,
      error: { kind: "Invalid", message: "Some of the details need correcting.", fields },
    };
  }
  try {
    const value = await db.transaction((tx) => op.run({ actor, input: parsed.data, tx }));
    return { ok: true, value };
  } catch (error) {
    if (error instanceof DomainError) {
      return {
        ok: false,
        error: { kind: error.kind, message: error.message, fields: error.fields },
      };
    }
    const reference = options.report?.(error);
    return {
      ok: false,
      error: {
        kind: "Unavailable",
        message: "Something went wrong on our side. Try again in a moment.",
        reference,
      },
    };
  }
}
