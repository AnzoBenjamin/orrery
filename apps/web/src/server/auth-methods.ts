import { createServerFn } from "@tanstack/react-start";
import { serverEnv } from "./env.ts";

/** Which OAuth providers this deployment has configured, so the UI offers only working ones. */
export const getAuthMethods = createServerFn({ method: "GET" }).handler(async () => {
  const env = serverEnv();
  return {
    github: Boolean(env.GITHUB_CLIENT_ID && env.GITHUB_CLIENT_SECRET),
    google: Boolean(env.GOOGLE_CLIENT_ID && env.GOOGLE_CLIENT_SECRET),
  };
});
