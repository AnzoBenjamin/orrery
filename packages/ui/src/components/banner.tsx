import type { ReactNode } from "react";

export type BannerTone = "error" | "success" | "info";

const tones: Record<BannerTone, { box: string; mark: string; label: string }> = {
  // Oxblood and verdigris are too dark for text on the dark surfaces (see tokens.ts), so errors use
  // an oxblood fill under bone text and success uses a verdigris rule beside bone text.
  error: { box: "bg-oxblood text-bone", mark: "✕", label: "Error" },
  success: { box: "border-l-4 border-verdigris bg-umber text-bone", mark: "✓", label: "Done" },
  info: { box: "border-l-4 border-brass bg-umber text-bone", mark: "§", label: "Note" },
};

/**
 * A message about the result of an action. Errors are announced immediately (role="alert");
 * other tones politely (role="status").
 */
export function Banner(props: { tone: BannerTone; title: string; children?: ReactNode }) {
  const tone = tones[props.tone];
  return (
    <div
      role={props.tone === "error" ? "alert" : "status"}
      className={`flex gap-3 px-4 py-3 font-interface ${tone.box}`}
    >
      <span aria-hidden="true" className="font-instrument">
        {tone.mark}
      </span>
      <div>
        <p className="font-semibold">
          <span className="sr-only">{tone.label}: </span>
          {props.title}
        </p>
        {props.children ? <div className="mt-1 text-sm">{props.children}</div> : null}
      </div>
    </div>
  );
}
