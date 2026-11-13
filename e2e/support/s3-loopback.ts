import { createConnection, createServer, type Server } from "node:net";

/**
 * Presigned URLs name the object store's public endpoint, http://localhost:<port>. The test
 * browser runs in the web container's network namespace, where nothing listens on that port, so
 * this forwards it to Garage on the Compose network. The Host header the browser signs and sends
 * stays localhost:<port>, so signatures still match. Started once per run (Playwright
 * globalSetup) and bound to the loopback interface only.
 */
export async function startS3Loopback(publicUrl: string, target: { host: string; port: number }) {
  const { hostname, port } = new URL(publicUrl);
  if (hostname !== "localhost" && hostname !== "127.0.0.1") return async () => undefined;
  const server: Server = createServer((client) => {
    const upstream = createConnection(target);
    client.pipe(upstream).pipe(client);
    const close = () => {
      client.destroy();
      upstream.destroy();
    };
    client.on("error", close);
    upstream.on("error", close);
  });
  const listening = await new Promise<boolean>((resolve, reject) => {
    server.once("error", (error: NodeJS.ErrnoException) =>
      error.code === "EADDRINUSE" ? resolve(false) : reject(error),
    );
    server.listen(Number(port), "127.0.0.1", () => resolve(true));
  });
  // Something already serves the port (a developer's own forwarder): use it.
  if (!listening) return async () => undefined;
  return () => new Promise<void>((resolve) => server.close(() => resolve()));
}
