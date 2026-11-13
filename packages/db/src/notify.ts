import pg from "pg";

export interface Listener {
  /**
   * Calls `handler` with each NOTIFY payload on `channel` until the returned function is called.
   * Many subscribers share one LISTEN per channel. After a reconnect every handler is called with
   * null, because notifications sent while disconnected are lost and callers must re-read.
   */
  subscribe(
    channel: string,
    handler: (payload: string | null) => void,
  ): Promise<() => Promise<void>>;
  close(): Promise<void>;
}

/**
 * One dedicated connection, outside the pool, for LISTEN (tech.md: listeners use a dedicated
 * connection). It reconnects with backoff and re-subscribes every channel.
 */
export function createListener(options: {
  connectionString: string;
  applicationName: string;
  onError?: (error: unknown) => void;
}): Listener {
  const handlers = new Map<string, Set<(payload: string | null) => void>>();
  let client: pg.Client | undefined;
  let connecting: Promise<pg.Client> | undefined;
  let closed = false;
  let retryMs = 250;

  const listen = (c: pg.Client, channel: string) =>
    c.query(`LISTEN ${c.escapeIdentifier(channel)}`);

  function connect(): Promise<pg.Client> {
    if (client) return Promise.resolve(client);
    connecting ??= (async () => {
      const c = new pg.Client({
        connectionString: options.connectionString,
        application_name: options.applicationName,
      });
      c.on("notification", (msg) => {
        for (const h of handlers.get(msg.channel) ?? []) h(msg.payload ?? null);
      });
      c.on("error", (error) => {
        options.onError?.(error);
        drop(c);
      });
      c.on("end", () => drop(c));
      await c.connect();
      for (const channel of handlers.keys()) await listen(c, channel);
      client = c;
      retryMs = 250;
      return c;
    })().finally(() => {
      connecting = undefined;
    });
    return connecting;
  }

  function drop(c: pg.Client) {
    if (client !== c) return;
    client = undefined;
    c.end().catch(() => undefined);
    if (closed || handlers.size === 0) return;
    const wait = retryMs;
    retryMs = Math.min(retryMs * 2, 10_000);
    setTimeout(() => {
      connect().then(
        () => {
          for (const set of handlers.values()) for (const h of set) h(null);
        },
        (error: unknown) => {
          options.onError?.(error);
          if (!closed) drop(c);
        },
      );
    }, wait).unref();
  }

  return {
    async subscribe(channel, handler) {
      let set = handlers.get(channel);
      const first = !set;
      if (!set) {
        set = new Set();
        handlers.set(channel, set);
      }
      set.add(handler);
      const c = await connect();
      if (first && client === c) await listen(c, channel);
      return async () => {
        set.delete(handler);
        if (set.size === 0 && handlers.get(channel) === set) {
          handlers.delete(channel);
          await client
            ?.query(`UNLISTEN ${client.escapeIdentifier(channel)}`)
            .catch(() => undefined);
        }
      };
    },
    async close() {
      closed = true;
      handlers.clear();
      const c = client;
      client = undefined;
      await c?.end();
    },
  };
}
