/**
 * The solver worker's side (mechanism-core requirements 9.1, 9.2, 9.4): one `Solver` per open
 * mechanism, requests answered in order, typed arrays transferred back.
 *
 * Latest wins: a request carries an optional channel, and requests are run on a later task than
 * the one that received them. A request still waiting when a newer one arrives on its channel is
 * answered `cancelled` without running, so a drag that sends a request per pointer move only
 * solves the latest pose. A request already running finishes; WebAssembly cannot be interrupted.
 */
import type { Envelope, Port, Reply, Request } from "./protocol.ts";

/** What the host needs from the WebAssembly module (`pkg/kinematics.js` after init). */
export interface WasmModule {
  Solver: new (graphJson: string) => WasmSolver;
  fit(problemJson: string): unknown;
}

interface WasmSolver {
  free(): void;
  stateSize(): number;
  driverCount(): number;
  pointNames(): unknown;
  assemble(drive: Float64Array | number[], seed?: Float64Array | null): Float64Array;
  pointPositions(state: Float64Array): Float64Array;
  simulate(
    driver: number,
    drive: Float64Array | number[],
    start: number,
    end: number,
    step: number,
    seed?: Float64Array | null,
  ): object;
  mobility(state: Float64Array, drive: Float64Array | number[]): unknown;
  plausibility(
    driver: number,
    drive: Float64Array | number[],
    start: number,
    end: number,
    step: number,
    seed?: Float64Array | null,
  ): unknown;
}

/** Errors thrown by the module are plain `{ kind, detail }` objects; anything else is internal. */
function toReplyError(error: unknown): Extract<Reply, { ok: false }>["error"] {
  if (typeof error === "object" && error !== null && "kind" in error) {
    return error as Extract<Reply, { ok: false }>["error"];
  }
  return { kind: "internal", message: error instanceof Error ? error.message : String(error) };
}

/** Typed arrays in a result, so their buffers can be transferred instead of copied. */
function buffersOf(value: unknown): ArrayBuffer[] {
  if (value instanceof Float64Array) return [value.buffer as ArrayBuffer];
  if (typeof value === "object" && value !== null) {
    return Object.values(value).flatMap((v) =>
      v instanceof Float64Array ? [v.buffer as ArrayBuffer] : [],
    );
  }
  return [];
}

export function serve(port: Port, wasm: WasmModule): void {
  const solvers = new Map<number, WasmSolver>();
  let nextHandle = 1;
  const queue: Envelope[] = [];
  let scheduled = false;

  const solverFor = (handle: number) => {
    const solver = solvers.get(handle);
    if (!solver) throw { kind: "internal", message: `Mechanism ${handle} is not open` };
    return solver;
  };

  const run = (request: Request): unknown => {
    switch (request.method) {
      case "open": {
        const solver = new wasm.Solver(request.graph);
        const id = nextHandle++;
        solvers.set(id, solver);
        return {
          id,
          stateSize: solver.stateSize(),
          driverCount: solver.driverCount(),
          pointNames: solver.pointNames(),
        };
      }
      case "close":
        solvers.get(request.handle)?.free();
        solvers.delete(request.handle);
        return null;
      case "assemble":
        return solverFor(request.handle).assemble(request.drive, request.seed ?? null);
      case "pointPositions":
        return solverFor(request.handle).pointPositions(request.state);
      case "simulate": {
        const r = request;
        return solverFor(r.handle).simulate(
          r.driver,
          r.drive,
          r.start,
          r.end,
          r.step,
          r.seed ?? null,
        );
      }
      case "mobility":
        return solverFor(request.handle).mobility(request.state, request.drive);
      case "plausibility": {
        const r = request;
        return solverFor(r.handle).plausibility(
          r.driver,
          r.drive,
          r.start,
          r.end,
          r.step,
          r.seed ?? null,
        );
      }
      case "fit":
        return wasm.fit(request.problem);
    }
  };

  const drain = () => {
    scheduled = false;
    while (queue.length > 0) {
      const envelope = queue.shift() as Envelope;
      let reply: Reply;
      try {
        reply = { id: envelope.id, ok: true, value: run(envelope) };
      } catch (error) {
        reply = { id: envelope.id, ok: false, error: toReplyError(error) };
      }
      port.postMessage(reply, reply.ok ? buffersOf(reply.value) : []);
    }
  };

  port.addEventListener("message", (event: MessageEvent) => {
    const envelope = event.data as Envelope;
    if (envelope.channel !== undefined) {
      // Supersede what is still waiting on this channel.
      for (let i = queue.length - 1; i >= 0; i--) {
        const waiting = queue[i];
        if (waiting && waiting.channel === envelope.channel) {
          queue.splice(i, 1);
          port.postMessage({
            id: waiting.id,
            ok: false,
            error: { kind: "cancelled" },
          } satisfies Reply);
        }
      }
    }
    queue.push(envelope);
    if (!scheduled) {
      scheduled = true;
      // A later task, so messages already sent are received (and can supersede) first.
      setTimeout(drain, 0);
    }
  });
}
