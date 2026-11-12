/** @jsxRuntime automatic */
/** @jsxImportSource react */
import { palette } from "@orrery/ui/tokens";
import {
  Body,
  Container,
  Head,
  Hr,
  Html,
  Link,
  Preview,
  Section,
  Text,
} from "@react-email/components";
import type { ReactNode } from "react";

/**
 * Shared frame for every Orrery email: an engraved plate on lamp-black paper. Mail clients ignore
 * web fonts and most CSS, so the display face falls back to Georgia and every style is inline.
 */
export function EmailLayout(props: {
  preview: string;
  plate: string;
  title: string;
  children: ReactNode;
  footer: ReactNode;
}) {
  return (
    <Html lang="en">
      <Head>
        <meta name="color-scheme" content="dark" />
        <meta name="supported-color-schemes" content="dark" />
      </Head>
      <Preview>{props.preview}</Preview>
      <Body style={{ backgroundColor: palette.lampblack, margin: 0, padding: "32px 0" }}>
        <Container
          style={{
            backgroundColor: palette.soot,
            border: `1px solid ${palette.umber}`,
            maxWidth: 560,
            padding: "36px 40px 28px",
          }}
        >
          <Text style={styles.wordmark}>Orrery</Text>
          <Text style={styles.plate}>{props.plate}</Text>
          <Text style={styles.title}>{props.title}</Text>
          <Hr style={styles.rule} />
          <Section>{props.children}</Section>
          <Hr style={styles.rule} />
          <Text style={styles.footer}>{props.footer}</Text>
        </Container>
      </Body>
    </Html>
  );
}

export function Paragraph({ children }: { children: ReactNode }) {
  return <Text style={styles.body}>{children}</Text>;
}

/** A brass call to action, with the raw URL beneath for clients that block buttons. */
export function Action({ href, label }: { href: string; label: string }) {
  return (
    <Section style={{ margin: "28px 0 8px" }}>
      <Link href={href} style={styles.button}>
        {label}
      </Link>
      <Text style={styles.fallback}>
        Or paste this address into your browser:
        <br />
        <Link href={href} style={{ color: palette.brassBright, wordBreak: "break-all" }}>
          {href}
        </Link>
      </Text>
    </Section>
  );
}

const display = '"IM Fell English", Georgia, "Times New Roman", serif';
const interfaceFont = '"IBM Plex Sans Condensed", "Arial Narrow", Arial, sans-serif';

export const styles = {
  wordmark: {
    color: palette.brass,
    fontFamily: display,
    fontSize: 15,
    letterSpacing: "0.18em",
    margin: 0,
    textTransform: "uppercase" as const,
  },
  plate: {
    color: palette.parchment,
    fontFamily: display,
    fontSize: 13,
    fontStyle: "italic",
    margin: "20px 0 0",
  },
  title: {
    color: palette.bone,
    fontFamily: display,
    fontSize: 28,
    lineHeight: "34px",
    margin: "4px 0 0",
  },
  rule: { borderColor: palette.umber, borderWidth: "1px 0 0", margin: "24px 0" },
  body: {
    color: palette.bone,
    fontFamily: interfaceFont,
    fontSize: 16,
    lineHeight: "24px",
    margin: "0 0 14px",
  },
  button: {
    backgroundColor: palette.brass,
    color: palette.lampblack,
    display: "inline-block",
    fontFamily: interfaceFont,
    fontSize: 16,
    fontWeight: 600,
    padding: "12px 22px",
    textDecoration: "none",
  },
  fallback: {
    color: palette.parchment,
    fontFamily: interfaceFont,
    fontSize: 13,
    lineHeight: "20px",
    margin: "16px 0 0",
  },
  footer: {
    color: palette.parchment,
    fontFamily: interfaceFont,
    fontSize: 13,
    lineHeight: "20px",
    margin: 0,
  },
  instrument: {
    color: palette.bone,
    fontFamily: '"IBM Plex Mono", Menlo, Consolas, monospace',
    fontSize: 14,
  },
} as const;
