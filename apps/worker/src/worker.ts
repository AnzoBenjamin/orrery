import { createServer, type Server } from "node:http";
import type { WorkerEnv } from "@orrery/config/worker";
import { assertMigrationsApplied, createDb } from "@orrery/db";
import { createMailer } from "@orrery/email";
import { allQueues, createWorkerBoss, emailSend, ensureQueues, work } from "@orrery/jobs";
import { emailSendHandler } from "./handlers/email-send.ts";
import type { Logger } from "./logger.ts";

export interface RunningWorker {
  /** Stops taking jobs, waits for running ones, then closes connections. */
  stop(): Promise<void>;
  /** Resolves to the bound port of the health endpoint (useful when started on port 0). */
  healthPort: number;
}

export async function startWorker(env: WorkerEnv, log: Logger): Promise<RunningWorker> {
  const database = createDb({
    connectionString: env.DATABASE_URL,
    max: 4,
    applicationName: "orrery-worker",
  });
  await assertMigrationsApplied(database.db);

  const mailer = createMailer({
    host: env.SMTP_HOST,
    port: env.SMTP_PORT,
    secure: env.SMTP_SECURE,
    user: env.SMTP_USER,
    password: env.SMTP_PASSWORD,
    from: env.MAIL_FROM,
  });

  const boss = createWorkerBoss(env.DATABASE_URL);
  boss.on("error", (error) => log.error({ err: error }, "pg-boss error"));
  await boss.start();
  await ensureQueues(boss, allQueues);
  await work(boss, emailSend, emailSendHandler({ mailer, log }), { concurrency: 2 });

  let healthy = true;
  const health: Server = createServer((req, res) => {
    if (req.url !== "/health") {
      res.writeHead(404).end();
      return;
    }
    database.pool
      .query("select 1")
      .then(() => {
        res.writeHead(healthy ? 200 : 503, { "content-type": "application/json" });
        res.end(JSON.stringify({ status: healthy ? "ok" : "stopping", database: "ok" }));
      })
      .catch(() => {
        res.writeHead(503, { "content-type": "application/json" });
        res.end(JSON.stringify({ status: "degraded", database: "unreachable" }));
      });
  });
  await new Promise<void>((resolve) => health.listen(env.WORKER_HEALTH_PORT, resolve));
  const address = health.address();
  const healthPort = typeof address === "object" && address ? address.port : env.WORKER_HEALTH_PORT;
  log.info({ queues: allQueues.map((q) => q.name), healthPort }, "worker started");

  return {
    healthPort,
    async stop() {
      healthy = false;
      await boss.stop({ graceful: true, timeout: 30_000 });
      mailer.close();
      await new Promise<void>((resolve) => health.close(() => resolve()));
      await database.close();
      log.info("worker stopped");
    },
  };
}
