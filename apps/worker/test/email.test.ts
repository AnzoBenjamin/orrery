import { parseWorkerEnv } from "@orrery/config/worker";
import { createTestDatabase, startTestPostgres, type TestPostgres } from "@orrery/db/testing";
import { createProducer, emailSend, enqueue, migrateJobSchema } from "@orrery/jobs";
import type { PgBoss } from "pg-boss";
import { GenericContainer, type StartedTestContainer, Wait } from "testcontainers";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { createLogger } from "../src/logger.ts";
import { type RunningWorker, startWorker } from "../src/worker.ts";

const MAILPIT_IMAGE =
  "axllent/mailpit:v1.33.1@sha256:aef2aacc11f075ec0fb6874275ee4a421e688e11a96ebb296134d1735c7761ce";

let postgres: TestPostgres;
let mailpit: StartedTestContainer;
let databaseClose: () => Promise<void>;
let worker: RunningWorker;
let producer: PgBoss;
let mailApi: string;

beforeAll(async () => {
  [postgres, mailpit] = await Promise.all([
    startTestPostgres(),
    new GenericContainer(MAILPIT_IMAGE)
      .withExposedPorts(1025, 8025)
      .withWaitStrategy(Wait.forHttp("/readyz", 8025))
      .start(),
  ]);
  mailApi = `http://${mailpit.getHost()}:${mailpit.getMappedPort(8025)}/api/v1`;
  const database = await createTestDatabase(postgres.adminUrl);
  databaseClose = database.close;
  await migrateJobSchema(database.url);

  const env = parseWorkerEnv({
    NODE_ENV: "test",
    LOG_LEVEL: "warn",
    DATABASE_URL: database.url,
    S3_ENDPOINT: "http://garage:3900",
    S3_PUBLIC_ENDPOINT: "http://localhost:53900",
    S3_REGION: "garage",
    S3_BUCKET: "orrery",
    S3_ACCESS_KEY_ID: "GK000000000000000000000000",
    S3_SECRET_ACCESS_KEY: "unused-in-this-test",
    SMTP_HOST: mailpit.getHost(),
    SMTP_PORT: String(mailpit.getMappedPort(1025)),
    MAIL_FROM: "Orrery <mail@orrery.test>",
    APP_URL: "http://localhost:53000",
    ENGINE_URL: "http://engine:8000",
    ENGINE_SERVICE_TOKEN: "unused-in-this-test-0123456789abcdef",
  });
  // Port 0 binds an ephemeral port, so parallel test runs never collide.
  worker = await startWorker({ ...env, WORKER_HEALTH_PORT: 0 }, createLogger("warn"));
  producer = createProducer(database.url);
  await producer.start();
});

afterAll(async () => {
  await producer?.stop({ graceful: false });
  await worker?.stop();
  await databaseClose?.();
  await Promise.all([postgres?.stop(), mailpit?.stop()]);
});

// Generous: the whole repository's suites start their containers at once under `make test`.
async function waitForMessageTo(address: string, timeoutMs = 45_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const res = await fetch(`${mailApi}/search?query=${encodeURIComponent(`to:${address}`)}`);
    const body = (await res.json()) as { messages: { ID: string; Subject: string }[] };
    if (body.messages.length > 0) return body.messages;
    await new Promise((r) => setTimeout(r, 250));
  }
  throw new Error(`no email to ${address} within ${timeoutMs} ms`);
}

describe("worker", () => {
  it("delivers a queued email through SMTP", async () => {
    const id = await enqueue(producer, emailSend, {
      message: {
        template: "verify-email",
        to: "lin@orrery.test",
        name: "Lin",
        url: "http://localhost:53000/verify?token=t1",
      },
    });
    expect(id).toEqual(expect.any(String));
    const messages = await waitForMessageTo("lin@orrery.test");
    expect(messages[0]?.Subject).toBe("Confirm your email address");
  });

  it("creates a keyed message once, even after it was sent", async () => {
    const message = {
      template: "reset-password" as const,
      to: "noor@orrery.test",
      name: "Noor",
      url: "http://localhost:53000/reset?token=r1",
    };
    const first = enqueue(producer, emailSend, { message, idempotencyKey: "reset:noor:1" });
    const second = enqueue(producer, emailSend, { message, idempotencyKey: "reset:noor:1" });
    const ids = (await Promise.all([first, second])).filter((x) => x !== null);
    expect(ids).toHaveLength(1);
    await waitForMessageTo("noor@orrery.test");
    expect(
      await enqueue(producer, emailSend, { message, idempotencyKey: "reset:noor:1" }),
    ).toBeNull();
    await new Promise((r) => setTimeout(r, 1500));
    expect(await waitForMessageTo("noor@orrery.test")).toHaveLength(1);
  });

  it("reports health", async () => {
    const res = await fetch(`http://127.0.0.1:${worker.healthPort}/health`);
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ status: "ok", database: "ok" });
  });
});
