import { EnvValidationError, toProblems } from "./errors.ts";

export type EnvSource = Record<string, string | undefined>;

/**
 * Options shared by every `createEnv` call: server-only parsing, empty strings treated as unset,
 * and failures raised as `EnvValidationError` naming each invalid variable.
 */
export function envOptions(processName: string, source: EnvSource) {
  return {
    runtimeEnv: source,
    emptyStringAsUndefined: true,
    isServer: true,
    onValidationError: (issues: Parameters<typeof toProblems>[0]): never => {
      throw new EnvValidationError(processName, toProblems(issues));
    },
  } as const;
}

/**
 * Process entry helper: returns the environment, or prints the problems to stderr and exits with
 * code 1.
 */
export function orExit<T>(load: () => T): T {
  try {
    return load();
  } catch (error) {
    if (error instanceof EnvValidationError) {
      process.stderr.write(`${error.message}\n`);
      process.exit(1);
    }
    throw error;
  }
}
