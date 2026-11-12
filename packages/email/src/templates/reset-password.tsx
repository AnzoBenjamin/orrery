/** @jsxRuntime automatic */
/** @jsxImportSource react */
import { Action, EmailLayout, Paragraph } from "./layout.tsx";

export function ResetPassword({ name, url }: { name: string; url: string }) {
  return (
    <EmailLayout
      preview="Choose a new password for your Orrery account."
      plate="Plate II"
      title="Reset your password"
      footer="If you did not ask to reset your password, ignore this message. Your password stays the same."
    >
      <Paragraph>{name},</Paragraph>
      <Paragraph>
        Someone asked to reset the password for this account. Choose a new one here:
      </Paragraph>
      <Action href={url} label="Choose a new password" />
      <Paragraph>The link works once and expires in 60 minutes.</Paragraph>
    </EmailLayout>
  );
}
