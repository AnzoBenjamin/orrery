/** @jsxRuntime automatic */
/** @jsxImportSource react */
import type { EmailMessage } from "@orrery/jobs";
import { render } from "@react-email/components";
import type { ReactElement } from "react";
import { AnalysisComplete } from "./templates/analysis-complete.tsx";
import { ResetPassword } from "./templates/reset-password.tsx";
import { SignInAlert } from "./templates/sign-in-alert.tsx";
import { VerifyEmail } from "./templates/verify-email.tsx";

export interface RenderedEmail {
  subject: string;
  html: string;
  text: string;
}

function select(message: EmailMessage): { subject: string; element: ReactElement } {
  switch (message.template) {
    case "verify-email":
      return {
        subject: "Confirm your email address",
        element: <VerifyEmail name={message.name} url={message.url} />,
      };
    case "reset-password":
      return {
        subject: "Reset your Orrery password",
        element: <ResetPassword name={message.name} url={message.url} />,
      };
    case "sign-in-alert":
      return {
        subject: "New sign-in to your Orrery account",
        element: (
          <SignInAlert
            name={message.name}
            at={message.at}
            device={message.device}
            ipPrefix={message.ipPrefix}
            sessionsUrl={message.sessionsUrl}
          />
        ),
      };
    case "analysis-complete":
      return {
        subject: `Analysis complete: ${message.specimenTitle}`,
        element: (
          <AnalysisComplete
            name={message.name}
            specimenTitle={message.specimenTitle}
            url={message.url}
            preferencesUrl={message.preferencesUrl}
          />
        ),
      };
  }
}

export async function renderEmail(message: EmailMessage): Promise<RenderedEmail> {
  const { subject, element } = select(message);
  const [html, text] = await Promise.all([render(element), render(element, { plainText: true })]);
  return { subject, html, text };
}
