/**
 * The typed Promise API to the solver worker (mechanism-core requirement 9.2).
 */
import type { Mechanism } from "@orrery/schema";
import type { Envelope, Port, Reply, Request, Results, SweepArgs } from "./protocol.ts";
import type {
  MechanismHandle,
  Mobility,
  Plausibility,
  Simulation,
  SolverErrorDetail,
} from "./types.ts";

/** The solver refused or failed: `detail` says how (`invalidGraph`, `assemblyFailed`, ...). */
export class SolverError extends Error {
  readonly detail: SolverErrorDetail | { kind: "internal"; message: string };
  constructor(detail: SolverErrorDetail | { kind: "internal"; message: string }) {
    super(detail.kind === "internal" ? detail.message : `solver: ${detail.kind}`);
    this.name = "SolverError";
    this.detail = detail;
  }
}

/** A newer request on the same channel replaced this one before it ran. */
export class Cancelled extends Error {
  constructor() {
    super("superseded by a newer request");
    this.name = "Cancelled";
  }
}

type Method = keyof Results;

export class SolverClient {
  private readonly port: Port;
  private nextId = 1;
  private readonly pending = new Map<
    number,
    { resolve: (v: unknown) => void; reject: (e: Error) => void }
  >();

  constructor(port: Port) {
    this.port = port;
    port.addEventListener("message", (event: MessageEvent) => {
      const reply = event.data as Reply;
      const waiter = this.pending.get(reply.id);
      if (!waiter) return;
      this.pending.delete(reply.id);
      if (reply.ok) waiter.resolve(reply.value);
      else if (reply.error.kind === "cancelled") waiter.reject(new Cancelled());
      else waiter.reject(new SolverError(reply.error));
    });
  }

  private send<M extends Method>(
    request: Request & { method: M },
    channel?: string,
  ): Promise<Results[M]> {
    const id = this.nextId++;
    const envelope: Envelope = { ...request, id, channel };
    return new Promise<Results[M]>((resolve, reject) => {
      this.pending.set(id, { resolve: resolve as (v: unknown) => void, reject });
      this.port.postMessage(envelope);
    });
  }

  /** Opens a mechanism graph in the worker. */
  open(graph: Mechanism): Promise<MechanismHandle> {
    return this.send({ method: "open", graph: JSON.stringify(graph) });
  }

  close(handle: MechanismHandle): Promise<null> {
    return this.send({ method: "close", handle: handle.id });
  }

  /**
   * Assembles for the driver values, keeping the seed's branch. Requests on the same `channel`
   * supersede each other: only the latest waiting one runs.
   */
  assemble(
    handle: MechanismHandle,
    drive: number[] | Float64Array,
    seed?: Float64Array,
    channel?: string,
  ): Promise<Float64Array> {
    return this.send({ method: "assemble", handle: handle.id, drive, seed }, channel);
  }

  pointPositions(handle: MechanismHandle, state: Float64Array): Promise<Float64Array> {
    return this.send({ method: "pointPositions", handle: handle.id, state });
  }

  simulate(handle: MechanismHandle, sweep: SweepArgs, channel?: string): Promise<Simulation> {
    return this.send({ method: "simulate", handle: handle.id, ...sweep }, channel);
  }

  mobility(
    handle: MechanismHandle,
    state: Float64Array,
    drive: number[] | Float64Array,
  ): Promise<Mobility> {
    return this.send({ method: "mobility", handle: handle.id, state, drive });
  }

  plausibility(handle: MechanismHandle, sweep: SweepArgs, channel?: string): Promise<Plausibility> {
    return this.send({ method: "plausibility", handle: handle.id, ...sweep }, channel);
  }

  /** Fits a `kinematics::fit::FitProblem` (camelCase JSON); returns the `FitResult`. */
  fit(problem: unknown): Promise<unknown> {
    return this.send({ method: "fit", problem: JSON.stringify(problem) });
  }
}
