/** @jsxRuntime automatic */
/** @jsxImportSource react */
import { Text } from "@react-email/components";
import { Action, EmailLayout, Paragraph, styles } from "./layout.tsx";

export function SignInAlert(props: {
  name: string;
  at: string;
  device: string;
  ipPrefix: string;
  sessionsUrl: string;
}) {
  const when = new Date(props.at).toUTCString();
  return (
    <EmailLayout
      preview={`New sign-in to Orrery from ${props.device}.`}
      plate="Plate III"
      title="New sign-in to your account"
      footer="You receive this message whenever your account is used from a device or network we have not seen before."
    >
      <Paragraph>{props.name},</Paragraph>
      <Paragraph>Your account was just used from a new device or network:</Paragraph>
      <Text style={{ ...styles.instrument, margin: "0 0 16px", lineHeight: "24px" }}>
        {props.device}
        <br />
        Network {props.ipPrefix}
        <br />
        {when}
      </Text>
      <Paragraph>
        If this was you, there is nothing to do. If not, sign out that session and change your
        password.
      </Paragraph>
      <Action href={props.sessionsUrl} label="Review active sessions" />
    </EmailLayout>
  );
}
