/** The Standard Schema issue shape that @t3-oss/env-core passes to `onValidationError`. */
interface SchemaIssue {
  readonly message: string;
  readonly path?: ReadonlyArray<PropertyKey | { readonly key: PropertyKey }> | undefined;
}

/** One invalid environment variable: its name and the reason, never its value. */
export interface EnvProblem {
  readonly variable: string;
  readonly reason: string;
}

/**
 * Startup configuration failure. The message lists variable names and validation reasons only.
 * Schemas in this package use messages that do not echo input, so values (secrets included) never
 * reach logs.
 */
export class EnvValidationError extends Error {
  readonly problems: readonly EnvProblem[];

  constructor(processName: string, problems: readonly EnvProblem[]) {
    const lines = problems.map((p) => `  ${p.variable}: ${p.reason}`);
    super(`Invalid environment for ${processName}:\n${lines.join("\n")}`);
    this.name = "EnvValidationError";
    this.problems = problems;
  }

  get variables(): string[] {
    return [...new Set(this.problems.map((p) => p.variable))];
  }
}

export function toProblems(issues: readonly SchemaIssue[]): EnvProblem[] {
  return issues.map((issue) => {
    const first = issue.path?.[0];
    const key = typeof first === "object" ? first.key : first;
    return { variable: key === undefined ? "(environment)" : String(key), reason: issue.message };
  });
}
