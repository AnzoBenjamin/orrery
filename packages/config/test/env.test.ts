import { execFile } from "node:child_process";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";
import { describe, expect, expectTypeOf, it } from "vitest";
import { EnvValidationError } from "../src/index.ts";
import { parseWebPublicEnv, parseWebServerEnv } from "../src/web.ts";
import { parseWorkerEnv } from "../src/worker.ts";

const worker = {
  DATABASE_URL: "postgres://orrery:pw@postgres:5432/orrery",
  S3_ENDPOINT: "http://garage:3900",
  S3_PUBLIC_ENDPOINT: "http://localhost:53900",
  S3_REGION: "garage",
  S3_BUCKET: "orrery",
  S3_ACCESS_KEY_ID: "GK0123456789abcdef01234567",
  S3_SECRET_ACCESS_KEY: "secret-access-key-value",
  SMTP_HOST: "mailpit",
  SMTP_PORT: "1025",
  MAIL_FROM: "Orrery <mail@orrery.example>",
  APP_URL: "http://localhost:53000",
};

const web = {
  DATABASE_URL: worker.DATABASE_URL,
  S3_ENDPOINT: worker.S3_ENDPOINT,
  S3_PUBLIC_ENDPOINT: worker.S3_PUBLIC_ENDPOINT,
  S3_REGION: worker.S3_REGION,
  S3_BUCKET: worker.S3_BUCKET,
  S3_ACCESS_KEY_ID: worker.S3_ACCESS_KEY_ID,
  S3_SECRET_ACCESS_KEY: worker.S3_SECRET_ACCESS_KEY,
  BETTER_AUTH_URL: "http://localhost:53000",
  BETTER_AUTH_SECRET: "a".repeat(64),
};

function problemsOf(run: () => unknown): Record<string, string> {
  try {
    run();
  } catch (error) {
    if (error instanceof EnvValidationError) {
      return Object.fromEntries(error.problems.map((p) => [p.variable, p.reason]));
    }
    throw error;
  }
  throw new Error("expected validation to fail");
}

describe("worker environment", () => {
  it("applies defaults and coerces numbers and booleans", () => {
    const env = parseWorkerEnv({ ...worker, SMTP_SECURE: "true" });
    expect(env.NODE_ENV).toBe("development");
    expect(env.LOG_LEVEL).toBe("info");
    expect(env.SMTP_PORT).toBe(1025);
    expect(env.SMTP_SECURE).toBe(true);
    expect(env.WORKER_HEALTH_PORT).toBe(9090);
    expectTypeOf(env.SMTP_PORT).toEqualTypeOf<number>();
    expectTypeOf(env.OTEL_EXPORTER_OTLP_ENDPOINT).toEqualTypeOf<string | undefined>();
  });

  it("treats empty strings as unset", () => {
    expect(problemsOf(() => parseWorkerEnv({ ...worker, APP_URL: "" }))).toHaveProperty("APP_URL");
  });

  it("lists every invalid variable in one error", () => {
    const problems = problemsOf(() => parseWorkerEnv({}));
    for (const key of ["DATABASE_URL", "S3_BUCKET", "SMTP_HOST", "APP_URL", "MAIL_FROM"]) {
      expect(problems).toHaveProperty(key);
    }
  });

  it("rejects SMTP credentials without a password", () => {
    const problems = problemsOf(() => parseWorkerEnv({ ...worker, SMTP_USER: "orrery" }));
    expect(problems.SMTP_PASSWORD).toBe("must be set together with SMTP_USER");
  });

  it("requires telemetry and error reporting in production", () => {
    const problems = problemsOf(() => parseWorkerEnv({ ...worker, NODE_ENV: "production" }));
    expect(problems.OTEL_EXPORTER_OTLP_ENDPOINT).toBe("is required in production");
    expect(problems.SENTRY_DSN).toBe("is required in production");
  });
});

describe("web environment", () => {
  it("accepts a development environment without OAuth providers", () => {
    const env = parseWebServerEnv(web);
    expect(env.GITHUB_CLIENT_ID).toBeUndefined();
  });

  it("rejects half-configured OAuth providers", () => {
    const problems = problemsOf(() => parseWebServerEnv({ ...web, GITHUB_CLIENT_ID: "abc" }));
    expect(problems.GITHUB_CLIENT_SECRET).toBe("must be set together with GITHUB_CLIENT_ID");
  });

  it("requires OAuth, telemetry, and https in production", () => {
    const problems = problemsOf(() => parseWebServerEnv({ ...web, NODE_ENV: "production" }));
    expect(Object.keys(problems).sort()).toEqual([
      "BETTER_AUTH_URL",
      "GITHUB_CLIENT_ID",
      "GITHUB_CLIENT_SECRET",
      "GOOGLE_CLIENT_ID",
      "GOOGLE_CLIENT_SECRET",
      "OTEL_EXPORTER_OTLP_ENDPOINT",
      "SENTRY_DSN",
    ]);
    expect(problems.BETTER_AUTH_URL).toBe("must use https in production");
  });

  it("allows scaled auth rate limits outside production only", () => {
    expect(parseWebServerEnv({ ...web, AUTH_RATE_LIMIT_SCALE: "20" }).AUTH_RATE_LIMIT_SCALE).toBe(
      20,
    );
    const problems = problemsOf(() =>
      parseWebServerEnv({ ...web, NODE_ENV: "production", AUTH_RATE_LIMIT_SCALE: "20" }),
    );
    expect(problems.AUTH_RATE_LIMIT_SCALE).toBe("must be 1 in production");
  });

  it("exposes only PUBLIC_ variables to the browser schema", () => {
    const env = parseWebPublicEnv({
      ...web,
      PUBLIC_SENTRY_DSN: "https://key@glitchtip.orrery.example/1",
    });
    expect(Object.keys(env)).toEqual(["PUBLIC_SENTRY_DSN"]);
  });
});

describe("process startup", () => {
  const run = promisify(execFile);
  const entry = fileURLToPath(new URL("../src/worker.ts", import.meta.url));

  it("exits non-zero and names invalid variables without printing their values", async () => {
    const script = `import(${JSON.stringify(entry)}).then((m) => m.loadWorkerEnv())`;
    const secret = "f".repeat(20);
    const failure = await run(process.execPath, ["--input-type=module", "-e", script], {
      env: {
        PATH: process.env.PATH,
        ...worker,
        DATABASE_URL: `mysql://orrery:${secret}@db/orrery`,
      },
    }).then(
      () => null,
      (error: { code: number; stderr: string }) => error,
    );
    expect(failure?.code).toBe(1);
    expect(failure?.stderr).toContain("Invalid environment for worker:");
    expect(failure?.stderr).toContain("DATABASE_URL: must be a postgres:// URL");
    expect(failure?.stderr).not.toContain(secret);
  });
});
