import type { ReactNode } from "react";

export type BannerTone = "error" | "success" | "info";

const marks: Record<BannerTone, { mark: string; label: string }> = {
  error: { mark: "✕", label: "Error" },
  success: { mark: "✓", label: "Done" },
  info: { mark: "§", label: "Note" },
};

/**
 * A message about the result of an action. Errors are an oxblood slip under bone lettering (legible
 * on paper and on the dark desk); other tones are a ruled note in the surface's own ink. Errors
 * are announced at once (role="alert"), others politely (role="status").
 */
export function Banner(props: { tone: BannerTone; title: string; children?: ReactNode }) {
  const { mark, label } = marks[props.tone];
  const box =
    props.tone === "error"
      ? "bg-oxblood text-bone shadow-[inset_0_0_0_1px_rgb(14_13_11/0.35)]"
      : "border-l-2 border-[var(--ink)] text-[var(--ink)]";
  return (
    <div
      role={props.tone === "error" ? "alert" : "status"}
      className={`flex gap-3 px-4 py-3 ${box}`}
    >
      <span aria-hidden="true" className="font-display text-lg leading-6">
        {mark}
      </span>
      <div className="leading-6">
        <p className="font-display text-[1.05rem]">
          <span className="sr-only">{label}: </span>
          {props.title}
        </p>
        {props.children ? <div className="mt-1 text-sm opacity-90">{props.children}</div> : null}
      </div>
    </div>
  );
}
