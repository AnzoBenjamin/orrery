/** @jsxRuntime automatic */
/** @jsxImportSource react */
import { palette } from "@orrery/ui/tokens";
import { Link } from "@react-email/components";
import { Action, EmailLayout, Paragraph } from "./layout.tsx";

export function AnalysisComplete(props: {
  name: string;
  specimenTitle: string;
  url: string;
  preferencesUrl: string;
}) {
  return (
    <EmailLayout
      preview={`The analysis of ${props.specimenTitle} is ready.`}
      plate="Plate IV"
      title="Analysis complete"
      footer={
        <>
          You asked to be told when an analysis finishes.{" "}
          <Link href={props.preferencesUrl} style={{ color: palette.brassBright }}>
            Turn these emails off
          </Link>
          .
        </>
      }
    >
      <Paragraph>{props.name},</Paragraph>
      <Paragraph>
        The engine has finished reconstructing <strong>{props.specimenTitle}</strong>. Open the
        workbench to inspect the mechanism, answer any questions the engine left for you, and run
        the simulation.
      </Paragraph>
      <Action href={props.url} label="Open the workbench" />
    </EmailLayout>
  );
}
