/** @jsxRuntime automatic */
/** @jsxImportSource react */
import { Action, EmailLayout, Paragraph } from "./layout.tsx";

export function VerifyEmail({ name, url }: { name: string; url: string }) {
  return (
    <EmailLayout
      preview="Confirm your email address to activate your Orrery account."
      plate="Plate I"
      title="Confirm your email address"
      footer="If you did not create an Orrery account, ignore this message and no account will be activated."
    >
      <Paragraph>{name},</Paragraph>
      <Paragraph>
        Confirm this address to activate your account. You can sign in and upload footage once it is
        confirmed.
      </Paragraph>
      <Action href={url} label="Confirm email address" />
      <Paragraph>The link works once and expires in 24 hours.</Paragraph>
    </EmailLayout>
  );
}
