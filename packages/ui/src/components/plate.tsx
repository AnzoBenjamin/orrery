import type { ReactNode } from "react";
import { toRoman } from "../roman.ts";

/**
 * An engraved plate: a double-ruled frame with a plate number and an optional caption, as in
 * nineteenth-century engineering plates. Used for focused surfaces such as the auth screens.
 */
export function Plate(props: {
  number: number;
  title: string;
  caption?: string | undefined;
  children: ReactNode;
  className?: string | undefined;
}) {
  return (
    <section
      aria-labelledby={`plate-${props.number}-title`}
      className={`border border-umber bg-soot p-1.5 ${props.className ?? ""}`}
    >
      <div className="border border-brass/40 px-7 pt-6 pb-8 sm:px-10">
        <p className="font-display-sc text-parchment text-sm tracking-[0.12em]">
          Plate {toRoman(props.number)}
        </p>
        <h1
          id={`plate-${props.number}-title`}
          className="mt-1 font-display text-3xl text-bone leading-tight"
        >
          {props.title}
        </h1>
        {props.caption ? (
          <p className="mt-2 font-display text-base text-parchment italic">{props.caption}</p>
        ) : null}
        <div className="mt-6 border-umber border-t pt-6">{props.children}</div>
      </div>
    </section>
  );
}
