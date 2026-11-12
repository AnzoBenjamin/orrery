import { loadWebServerEnv, type WebServerEnv } from "@orrery/config/web";

let cached: WebServerEnv | undefined;

/** The validated server environment. The process exits on first use if it is invalid. */
export function serverEnv(): WebServerEnv {
  cached ??= loadWebServerEnv();
  return cached;
}
