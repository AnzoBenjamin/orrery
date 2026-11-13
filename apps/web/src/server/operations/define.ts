import type { Db, Executor } from "@orrery/db";
import type { QueueDefinition } from "@orrery/jobs";
import type { Storage } from "@orrery/storage";
import type { z } from "zod";
import type { Actor } from "../actor.ts";
import { DomainError, type Result } from "../domain-errors.ts";
import type { Limit } from "../rate-limits.ts";

/** The outside systems operations use besides the database. Tests pass real instances. */
export interface Services {
  storage: Storage;
  /** Footage bytes one user may store. */
  quotaBytes: number;
  enqueue: <S extends z.ZodType>(queue: QueueDefinition<S>, payload: z.input<S>) => Promise<void>;
  /** Counts one request against a rate limit; throws RateLimited past it. */
  limit: Limit;
}

/** Facts about the HTTP request an operation runs for. */
export interface RequestInfo {
  /** The client's address as reported by the proxy, or null when unknown. */
  ip: string | null;
}

export interface Deps {
  db: Db;
  services: Services;
}

export interface OperationContext<TInput> {
  actor: Actor;
  input: TInput;
  /** An open transaction; the operation commits only if `run` resolves. */
  tx: Executor;
  services: Services;
  request: RequestInfo;
  /**
   * Runs `effect` once the transaction has committed, such as publishing a job about rows the
   * transaction wrote. Effects must be safe to lose: a failure is reported, not returned, and a
   * reconciling job repairs what it left undone.
   */
  afterCommit: (effect: () => Promise<void>) => void;
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
  request?: RequestInfo;
}

/** Validates input, runs the operation in a transaction, and maps errors to a Result. */
export async function invoke<TSchema extends z.ZodObject, TOutput>(
  deps: Deps,
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
  const effects: (() => Promise<void>)[] = [];
  let value: TOutput;
  try {
    value = await deps.db.transaction((tx) =>
      op.run({
        actor,
        input: parsed.data,
        tx,
        services: deps.services,
        request: options.request ?? { ip: null },
        afterCommit: (effect) => effects.push(effect),
      }),
    );
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
  for (const effect of effects) {
    await effect().catch((error: unknown) => options.report?.(error));
  }
  return { ok: true, value };
}
