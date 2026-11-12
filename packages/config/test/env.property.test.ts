import fc from "fast-check";
import { describe, expect, it } from "vitest";
import { EnvValidationError } from "../src/index.ts";
import { parseWebServerEnv } from "../src/web.ts";
import { parseWorkerEnv } from "../src/worker.ts";
import {
  invalidValue,
  SECRET_KEYS,
  validProductionWebEnv,
  validWebEnv,
  validWorkerEnv,
} from "./arbitraries.ts";

/**
 * Correctness property 5 (platform-foundation design): for any environment object, startup
 * validation accepts it if and only if it satisfies the schema, and error output never contains
 * secret values. Validates requirements 2.1 and 2.2.
 */

function captureError(run: () => unknown): EnvValidationError {
  try {
    run();
  } catch (error) {
    if (error instanceof EnvValidationError) return error;
    throw error;
  }
  throw new Error("expected validation to fail");
}

function expectNoSecretsIn(text: string, env: Record<string, string>, extra: string[] = []) {
  for (const key of SECRET_KEYS) {
    const value = env[key];
    if (value !== undefined && value.length >= 8) expect(text).not.toContain(value);
  }
  for (const value of extra) if (value.length >= 8) expect(text).not.toContain(value);
}

const processes = [
  { name: "worker", parse: parseWorkerEnv, valid: validWorkerEnv },
  { name: "web", parse: parseWebServerEnv, valid: validWebEnv },
  { name: "web (production)", parse: parseWebServerEnv, valid: validProductionWebEnv },
] as const;

describe.each(processes)("$name environment", ({ parse, valid }) => {
  it("accepts every environment that satisfies the schema", () => {
    fc.assert(
      fc.property(valid, (env) => {
        expect(() => parse(env)).not.toThrow();
      }),
    );
  });

  it("rejects a corrupted variable, names it, and never prints secret values", () => {
    const corruption = valid.chain((env) => {
      const keys = Object.keys(env).filter((k) => k in invalidValue);
      return fc
        .constantFrom(...keys)
        .chain((key) =>
          fc.tuple(fc.constant(env), fc.constant(key), invalidValue[key] ?? fc.constant("")),
        );
    });
    fc.assert(
      fc.property(corruption, ([env, key, bad]) => {
        const corrupted = { ...env, [key]: bad };
        const error = captureError(() => parse(corrupted));
        expect(error.variables).toContain(key);
        expectNoSecretsIn(error.message, corrupted, [bad]);
      }),
    );
  });

  it("rejects a missing required variable and names it", () => {
    const removal = valid.chain((env) =>
      fc.tuple(
        fc.constant(env),
        fc.constantFrom(
          ...Object.keys(env).filter((k) =>
            [
              "DATABASE_URL",
              "S3_ENDPOINT",
              "S3_BUCKET",
              "S3_SECRET_ACCESS_KEY",
              "APP_URL",
              "BETTER_AUTH_SECRET",
              "SMTP_HOST",
            ].includes(k),
          ),
        ),
      ),
    );
    fc.assert(
      fc.property(removal, ([env, key]) => {
        const { [key]: _removed, ...rest } = env;
        const error = captureError(() => parse(rest));
        expect(error.variables).toContain(key);
        expectNoSecretsIn(error.message, env);
      }),
    );
  });
});
