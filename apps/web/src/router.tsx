import { createRouter } from "@tanstack/react-router";
import { getGlobalStartContext } from "@tanstack/react-start";
import { routeTree } from "./routeTree.gen.ts";

const nonceOption = (nonce: string | undefined) => (nonce ? { nonce } : {});

export function getRouter() {
  return createRouter({
    routeTree,
    scrollRestoration: true,
    defaultPreload: "intent",
    // The request's CSP nonce, stamped on every script and style the router renders. In the
    // browser the router reads it back from the csp-nonce meta tag.
    ssr: nonceOption(getGlobalStartContext()?.nonce),
  });
}

declare module "@tanstack/react-router" {
  interface Register {
    router: ReturnType<typeof getRouter>;
  }
}
