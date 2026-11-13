import { createServer, type Server } from "node:http";
import type { WorkerEnv } from "@orrery/config/worker";
import { assertMigrationsApplied, createDb, deleteExpiredRequestLimits } from "@orrery/db";
import { createMailer } from "@orrery/email";
import {
  allQueues,
  createWorkerBoss,
  emailSend,
  enqueue,
  ensureQueues,
  footageProbe,
  limitsPrune,
  objectsDelete,
  scheduleQueue,
  uploadsReap,
  work,
} from "@orrery/jobs";
import { Storage } from "@orrery/storage";
import { createEngineClient } from "./engine.ts";
import { emailSendHandler } from "./handlers/email-send.ts";
import { footageProbeHandler } from "./handlers/footage-probe.ts";
import { objectsDeleteHandler } from "./handlers/objects-delete.ts";
import { uploadsReapHandler } from "./handlers/uploads-reap.ts";
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

  const storage = new Storage({
    endpoint: env.S3_ENDPOINT,
    publicEndpoint: env.S3_PUBLIC_ENDPOINT,
    region: env.S3_REGION,
    bucket: env.S3_BUCKET,
    accessKeyId: env.S3_ACCESS_KEY_ID,
    secretAccessKey: env.S3_SECRET_ACCESS_KEY,
  });
  const engine = createEngineClient({ url: env.ENGINE_URL, token: env.ENGINE_SERVICE_TOKEN });

  const boss = createWorkerBoss(env.DATABASE_URL);
  boss.on("error", (error) => log.error({ err: error }, "pg-boss error"));
  await boss.start();
  await ensureQueues(boss, allQueues);
  await work(boss, emailSend, emailSendHandler({ mailer, log }), { concurrency: 2 });
  // One probe at a time: the engine's analysis concurrency is 1 and probes share its CPU.
  await work(boss, footageProbe, footageProbeHandler({ db: database.db, storage, engine, log }));
  await work(boss, objectsDelete, objectsDeleteHandler({ db: database.db, storage, log }));
  await work(
    boss,
    uploadsReap,
    uploadsReapHandler({
      db: database.db,
      storage,
      enqueue: async (footageId) => {
        await enqueue(boss, footageProbe, { footageId });
      },
      log,
    }),
  );
  await work(boss, limitsPrune, async () => {
    const removed = await deleteExpiredRequestLimits(database.db, Date.now());
    if (removed > 0) log.info({ removed }, "expired rate-limit counters removed");
  });
  await scheduleQueue(boss, objectsDelete, "* * * * *", {});
  await scheduleQueue(boss, limitsPrune, "41 * * * *", {});
  await scheduleQueue(boss, uploadsReap, "17 * * * *", {});

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
      storage.destroy();
      await new Promise<void>((resolve) => health.close(() => resolve()));
      await database.close();
      log.info("worker stopped");
    },
  };
}
