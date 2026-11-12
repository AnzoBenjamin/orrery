import type { EmailMessage } from "@orrery/jobs";
import nodemailer, { type Transporter } from "nodemailer";
import { renderEmail } from "./render.tsx";

export interface MailerConfig {
  host: string;
  port: number;
  secure: boolean;
  user?: string | undefined;
  password?: string | undefined;
  from: string;
}

export interface Mailer {
  send(message: EmailMessage, options?: { messageId?: string | undefined }): Promise<void>;
  verify(): Promise<void>;
  close(): void;
}

/** Nodemailer over SMTP: Mailpit locally and in tests, Postfix with OpenDKIM in production. */
export function createMailer(config: MailerConfig): Mailer {
  const transport: Transporter = nodemailer.createTransport({
    host: config.host,
    port: config.port,
    secure: config.secure,
    ...(config.user && config.password
      ? { auth: { user: config.user, pass: config.password } }
      : {}),
    pool: true,
    maxConnections: 2,
  });
  return {
    async send(message, options = {}) {
      const rendered = await renderEmail(message);
      await transport.sendMail({
        from: config.from,
        to: { name: message.name, address: message.to },
        subject: rendered.subject,
        html: rendered.html,
        text: rendered.text,
        ...(options.messageId ? { messageId: options.messageId } : {}),
      });
    },
    async verify() {
      await transport.verify();
    },
    close() {
      transport.close();
    },
  };
}
