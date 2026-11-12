import appCss from "@orrery/ui/styles.css?url";
import {
  createRootRoute,
  HeadContent,
  Link,
  Outlet,
  Scripts,
  useRouter,
} from "@tanstack/react-router";
import type { ReactNode } from "react";
import { RouterProvider } from "react-aria-components";

export const Route = createRootRoute({
  head: () => ({
    meta: [
      { charSet: "utf-8" },
      { name: "viewport", content: "width=device-width, initial-scale=1" },
      { name: "color-scheme", content: "dark" },
      { name: "theme-color", content: "#0E0D0B" },
      { title: "Orrery" },
      {
        name: "description",
        content:
          "Orrery turns video of an old or broken machine into a simulated mechanism and proposes the missing part.",
      },
    ],
    links: [{ rel: "stylesheet", href: appCss }],
  }),
  component: RootComponent,
  notFoundComponent: NotFound,
  errorComponent: ({ error }) => <ErrorPage error={error} />,
});

function RootComponent() {
  const router = useRouter();
  return (
    <RootDocument>
      {/* Lets React Aria links navigate client-side through TanStack Router. */}
      <RouterProvider navigate={(to) => router.navigate({ to })} useHref={(to) => to}>
        <Outlet />
      </RouterProvider>
    </RootDocument>
  );
}

function RootDocument({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <head>
        <HeadContent />
      </head>
      <body>
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:bg-brass focus:px-3 focus:py-2 focus:text-lampblack"
        >
          Skip to content
        </a>
        {children}
        <Scripts />
      </body>
    </html>
  );
}

function NotFound() {
  return (
    <main id="main" className="mx-auto max-w-xl px-6 py-24">
      <p className="font-display-sc text-parchment text-sm tracking-[0.12em]">Plate missing</p>
      <h1 className="mt-1 font-display text-4xl text-bone">This page is not in the collection</h1>
      <p className="mt-4 text-parchment">
        The address may be mistyped, or the page was moved or removed.
      </p>
      <Link to="/" className="mt-6 inline-block text-brass-bright underline underline-offset-4">
        Return to Orrery
      </Link>
    </main>
  );
}

function ErrorPage({ error }: { error: unknown }) {
  return (
    <main id="main" className="mx-auto max-w-xl px-6 py-24">
      <p className="font-display-sc text-parchment text-sm tracking-[0.12em]">Fault</p>
      <h1 className="mt-1 font-display text-4xl text-bone">
        Something broke while loading this page
      </h1>
      <p className="mt-4 text-parchment">
        Reload the page to try again. If it keeps happening, the problem is on our side and we have
        been notified.
      </p>
      <p className="mt-4 font-instrument text-parchment text-sm">
        {error instanceof Error ? error.name : "Error"}
      </p>
    </main>
  );
}
