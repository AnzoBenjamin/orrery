import { loadWorkerEnv } from "@orrery/config/worker";
import { createLogger } from "./logger.ts";
import { startWorker } from "./worker.ts";

const env = loadWorkerEnv();
const log = createLogger(env.LOG_LEVEL);

try {
  const worker = await startWorker(env, log);
  let stopping = false;
  const shutdown = (signal: string) => {
    if (stopping) return;
    stopping = true;
    log.info({ signal }, "shutting down");
    worker.stop().then(
      () => process.exit(0),
      (error: unknown) => {
        log.error({ err: error }, "shutdown failed");
        process.exit(1);
      },
    );
  };
  process.on("SIGTERM", () => shutdown("SIGTERM"));
  process.on("SIGINT", () => shutdown("SIGINT"));
} catch (error) {
  log.fatal({ err: error }, "worker failed to start");
  process.exit(1);
}
