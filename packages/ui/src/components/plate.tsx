import type { ReactNode } from "react";
import { toRoman } from "../roman.ts";

/**
 * An engraved plate printed on bone paper: a heavy rule with a hairline inside, the plate number
 * set between ornamental rules, a display title, and an italic caption. Children inherit the
 * paper's ink colours through the .paper surface.
 */
export function Plate(props: {
  number: number;
  title: string;
  caption?: string | undefined;
  children: ReactNode;
  className?: string | undefined;
}) {
  const titleId = `plate-${props.number}-title`;
  return (
    <section aria-labelledby={titleId} className={`paper p-2.5 ${props.className ?? ""}`}>
      <div className="border-[1.5px] border-lampblack/80 p-1">
        <div className="border border-lampblack/40 px-6 pt-7 pb-8 sm:px-10">
          <p className="flex items-center gap-3 font-display-sc text-[0.95rem] text-umber tracking-[0.22em]">
            <span aria-hidden="true" className="h-px flex-1 bg-lampblack/30" />
            Plate {toRoman(props.number)}
            <span aria-hidden="true" className="h-px flex-1 bg-lampblack/30" />
          </p>
          <h1
            id={titleId}
            className="mt-4 text-center font-display text-[2.6rem] text-lampblack leading-[1.05]"
          >
            {props.title}
          </h1>
          {props.caption ? (
            <p className="mt-3 text-center font-display text-lg text-umber italic">
              {props.caption}
            </p>
          ) : null}
          <div aria-hidden="true" className="mx-auto mt-6 flex w-24 items-center gap-2">
            <span className="h-px flex-1 bg-lampblack/50" />
            <span className="size-1.5 rotate-45 bg-lampblack/70" />
            <span className="h-px flex-1 bg-lampblack/50" />
          </div>
          <div className="mt-7">{props.children}</div>
        </div>
      </div>
    </section>
  );
}
