import type { Mailer } from "@orrery/email";
import type { emailSend, JobContext, PayloadOf } from "@orrery/jobs";
import type { Logger } from "../logger.ts";

/**
 * Sends one email. The SMTP Message-ID is derived from the job id, so a retry after a lost
 * acknowledgement is recognisable as the same message downstream.
 */
export function emailSendHandler(deps: { mailer: Mailer; log: Logger }) {
  return async (payload: PayloadOf<typeof emailSend>, job: JobContext) => {
    await deps.mailer.send(payload.message, { messageId: `<${job.id}@jobs.orrery>` });
    deps.log.info(
      { job: job.id, template: payload.message.template, attempt: job.retryCount + 1 },
      "email sent",
    );
  };
}
