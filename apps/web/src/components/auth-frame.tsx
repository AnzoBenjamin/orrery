import { EngravedFourBar, Plate } from "@orrery/ui";
import { Link } from "@tanstack/react-router";
import type { ReactNode } from "react";

/**
 * Signed-out screens: a lamp-lit desk with the engraved figure of a mechanism missing its coupler,
 * and the register on bone paper beside it. On narrow screens the figure is dropped so the form
 * comes first.
 */
export function AuthFrame(props: {
  plate: number;
  title: string;
  caption?: string;
  children: ReactNode;
}) {
  return (
    <div className="lamp-light desk flex min-h-dvh flex-col text-bone">
      <header className="flex items-baseline justify-between px-6 pt-7 sm:px-12">
        <Link
          to="/"
          className="font-display-sc text-bone text-xl tracking-[0.32em] hover:text-brass-bright"
        >
          Orrery
        </Link>
        <p className="hidden font-display text-parchment italic md:block">
          The anatomist's workshop for broken machines
        </p>
      </header>
      <main
        id="main"
        className="mx-auto grid w-full max-w-[88rem] flex-1 items-center gap-10 px-4 py-8 lg:grid-cols-[1.45fr_1fr] lg:gap-12 lg:px-12"
      >
        <figure className="hidden lg:block">
          <EngravedFourBar className="h-auto w-full" />
        </figure>
        <Plate
          number={props.plate}
          title={props.title}
          caption={props.caption}
          className="w-full max-w-md justify-self-center lg:justify-self-end"
        >
          {props.children}
        </Plate>
      </main>
      <footer className="px-6 pb-6 font-display text-parchment text-sm italic sm:px-12">
        Footage in, mechanism out. Every proposal is checked against the motion before it is shown.
      </footer>
    </div>
  );
}
