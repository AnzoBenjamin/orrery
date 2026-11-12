import { Plate } from "@orrery/ui";
import { Link } from "@tanstack/react-router";
import type { ReactNode } from "react";

/** Page frame for the signed-out screens: wordmark, one plate, and a quiet footer. */
export function AuthFrame(props: {
  plate: number;
  title: string;
  caption?: string;
  children: ReactNode;
}) {
  return (
    <div className="lamp-light flex min-h-dvh flex-col">
      <header className="px-6 pt-8 sm:px-10">
        <Link
          to="/"
          className="font-display text-brass text-lg uppercase tracking-[0.2em] hover:text-brass-bright"
        >
          Orrery
        </Link>
      </header>
      <main id="main" className="flex flex-1 items-start justify-center px-4 py-10 sm:py-16">
        <Plate
          number={props.plate}
          title={props.title}
          caption={props.caption}
          className="w-full max-w-md"
        >
          {props.children}
        </Plate>
      </main>
    </div>
  );
}
