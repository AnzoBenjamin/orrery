/**
 * Results of the solver, as the WebAssembly module returns them (the `serde` forms of the
 * `kinematics` crate's types, camelCase). Lengths are meters, angles radians.
 */

export type Vec3 = [number, number, number];

export interface ValidationIssue {
  path: string;
  message: string;
}

export interface JointResidual {
  jointId: string;
  residual: number;
}

/** A typed solver failure (`kinematics::SolverError`). */
export type SolverErrorDetail =
  | { kind: "invalidGraph"; detail: ValidationIssue[] }
  | { kind: "assemblyFailed"; detail: { worstJoints: JointResidual[] } }
  | { kind: "driverCount"; detail: { expected: number; got: number } }
  | { kind: "seedLength"; detail: { expected: number; got: number } }
  | { kind: "fitDiverged"; detail: { iteration: number; cost: number } };

export interface Singularity {
  drive: number;
  kind: "dead_center" | "lockup" | "bifurcation";
  joints: string[];
}

export interface Simulation {
  /** The swept driver's value at each sample. */
  drive: Float64Array;
  /** `stateSize` numbers per sample. */
  states: Float64Array;
  /** `x, y, z` per named point (in `pointNames` order) per sample. */
  points: Float64Array;
  /** Inclusive driver ranges that could be assembled. */
  reachable: [number, number][];
  singularities: Singularity[];
}

export interface BodyMotion {
  bodyId: string;
  translation: Vec3;
  rotation: Vec3;
}

export interface Mobility {
  grubler: number;
  numerical: number;
  redundant: { jointId: string; rows: number }[];
  freeMotions: BodyMotion[][];
}

export interface Plausibility {
  loops: {
    bodies: [string, string, string, string];
    joints: [string, string, string, string];
    lengths: [number, number, number, number];
    grashof: "crank_rocker" | "double_crank" | "double_rocker" | "change_point" | "triple_rocker";
    transmission: { jointId: string; minAngle: number; at: number }[];
  }[];
  collisions: { bodies: [string, string]; ranges: [number, number][] }[];
  slenderness: [string, number][];
  reactionReversals: { jointId: string; at: number[]; peak: number }[];
}

/** An opened mechanism in the worker. */
export interface MechanismHandle {
  id: number;
  stateSize: number;
  driverCount: number;
  /** `[bodyId, pointId]` in the order point arrays use. */
  pointNames: [string, string][];
}
