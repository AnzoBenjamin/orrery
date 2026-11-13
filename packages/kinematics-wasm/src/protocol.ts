/** Messages between `SolverClient` and the solver worker (`host.ts`). */
import type {
  MechanismHandle,
  Mobility,
  Plausibility,
  Simulation,
  SolverErrorDetail,
} from "./types.ts";

export interface SweepArgs {
  driver: number;
  drive: Float64Array | number[];
  start: number;
  end: number;
  step: number;
  seed?: Float64Array | undefined;
}

export type Request =
  | { method: "open"; graph: string }
  | { method: "close"; handle: number }
  | {
      method: "assemble";
      handle: number;
      drive: Float64Array | number[];
      seed?: Float64Array | undefined;
    }
  | { method: "pointPositions"; handle: number; state: Float64Array }
  | ({ method: "simulate"; handle: number } & SweepArgs)
  | { method: "mobility"; handle: number; state: Float64Array; drive: Float64Array | number[] }
  | ({ method: "plausibility"; handle: number } & SweepArgs)
  | { method: "fit"; problem: string };

export interface Results {
  open: MechanismHandle;
  close: null;
  assemble: Float64Array;
  pointPositions: Float64Array;
  simulate: Simulation;
  mobility: Mobility;
  plausibility: Plausibility;
  fit: unknown;
}

/** A request on the wire: an id, and the channel whose older requests it supersedes. */
export type Envelope = Request & { id: number; channel?: string | undefined };

export type Reply =
  | { id: number; ok: true; value: unknown }
  | {
      id: number;
      ok: false;
      error: SolverErrorDetail | { kind: "cancelled" } | { kind: "internal"; message: string };
    };

/** The part of `MessagePort`, `Worker`, and a worker's `self` both ends use. */
export interface Port {
  postMessage(message: unknown, transfer?: Transferable[]): void;
  addEventListener(type: "message", listener: (event: MessageEvent) => void): void;
}
