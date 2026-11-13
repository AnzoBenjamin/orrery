import { startS3Loopback } from "./s3-loopback.ts";

export default async function globalSetup() {
  const publicUrl = process.env.E2E_S3_PUBLIC_URL;
  const target = process.env.E2E_S3_TARGET;
  if (!publicUrl || !target) return;
  const [host, port] = target.split(":");
  if (!host || !port) throw new Error("E2E_S3_TARGET must look like host:port");
  return startS3Loopback(publicUrl, { host, port: Number(port) });
}
