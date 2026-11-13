import { createMiddleware, createStart } from "@tanstack/react-start";
import { setResponseHeaders } from "@tanstack/react-start/server";
import { serverEnv } from "./server/env.ts";
import { createNonce, securityHeaders } from "./server/security-headers.ts";

/** Security headers and the CSP nonce on every response, pages and API routes alike. */
const securityMiddleware = createMiddleware().server(({ next }) => {
  const env = serverEnv();
  const nonce = createNonce();
  setResponseHeaders(
    new Headers(
      securityHeaders({
        nonce,
        objectStoreOrigin: new URL(env.S3_PUBLIC_ENDPOINT).origin,
        production: env.NODE_ENV === "production",
      }),
    ),
  );
  return next({ context: { nonce } });
});

export const startInstance = createStart(() => ({ requestMiddleware: [securityMiddleware] }));

declare module "@tanstack/react-start" {
  interface Register {
    config: Awaited<ReturnType<typeof startInstance.getOptions>>;
  }
}
