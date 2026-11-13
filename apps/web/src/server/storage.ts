import { Storage } from "@orrery/storage";
import { serverEnv } from "./env.ts";

let instance: Storage | undefined;

/** The web app's object store client, created on first use. */
export function storage(): Storage {
  if (!instance) {
    const env = serverEnv();
    instance = new Storage({
      endpoint: env.S3_ENDPOINT,
      publicEndpoint: env.S3_PUBLIC_ENDPOINT,
      region: env.S3_REGION,
      bucket: env.S3_BUCKET,
      accessKeyId: env.S3_ACCESS_KEY_ID,
      secretAccessKey: env.S3_SECRET_ACCESS_KEY,
    });
  }
  return instance;
}
