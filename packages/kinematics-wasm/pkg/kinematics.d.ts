/* tslint:disable */
/* eslint-disable */

/**
 * The solver for one mechanism graph.
 */
export class Solver {
    free(): void;
    [Symbol.dispose](): void;
    /**
     * Assembles for the driver values, from `seed` when given (keeping its branch).
     */
    assemble(drive: Float64Array | number[], seed?: Float64Array | number[] | null): Float64Array;
    /**
     * Number of drivers, in graph order.
     */
    driverCount(): number;
    /**
     * Grübler and numerical mobility, redundant joints, and free motions at `state`.
     */
    mobility(state: Float64Array | number[], drive: Float64Array | number[]): any;
    /**
     * Builds the solver from a mechanism graph document (JSON text).
     */
    constructor(graph_json: string);
    /**
     * Transmission angles, Grashof classes, collisions, and fabrication risk over a sweep.
     */
    plausibility(driver: number, drive: Float64Array | number[], start: number, end: number, step: number, seed?: Float64Array | number[] | null): any;
    /**
     * `[bodyId, pointId]` pairs, in the order of every point array.
     */
    pointNames(): any;
    /**
     * World positions of every named point at `state`, as `x, y, z` triples.
     */
    pointPositions(state: Float64Array | number[]): Float64Array;
    /**
     * Sweeps driver `driver` from `start` to `end` by `step`. Returns `{ drive, states, points,
     * reachable, singularities }`: `drive` per sample, `states` and `points` (point triples)
     * flattened sample by sample.
     */
    simulate(driver: number, drive: Float64Array | number[], start: number, end: number, step: number, seed?: Float64Array | number[] | null): object;
    /**
     * Length of a state vector.
     */
    stateSize(): number;
}

/**
 * Fits geometry, driver values, and camera parameters (a `FitProblem` as JSON text).
 */
export function fit(problem_json: string): any;

export type InitInput = RequestInfo | URL | Response | BufferSource | WebAssembly.Module;

export interface InitOutput {
    readonly memory: WebAssembly.Memory;
    readonly __wbg_solver_free: (a: number, b: number) => void;
    readonly fit: (a: number, b: number) => [number, number, number];
    readonly solver_assemble: (a: number, b: number, c: number, d: number, e: number) => [number, number, number];
    readonly solver_driverCount: (a: number) => number;
    readonly solver_mobility: (a: number, b: number, c: number, d: number, e: number) => [number, number, number];
    readonly solver_new: (a: number, b: number) => [number, number, number];
    readonly solver_plausibility: (a: number, b: number, c: number, d: number, e: number, f: number, g: number, h: number, i: number) => [number, number, number];
    readonly solver_pointNames: (a: number) => [number, number, number];
    readonly solver_pointPositions: (a: number, b: number, c: number) => [number, number, number];
    readonly solver_simulate: (a: number, b: number, c: number, d: number, e: number, f: number, g: number, h: number, i: number) => [number, number, number];
    readonly solver_stateSize: (a: number) => number;
    readonly __wbindgen_malloc: (a: number, b: number) => number;
    readonly __wbindgen_realloc: (a: number, b: number, c: number, d: number) => number;
    readonly __wbindgen_free: (a: number, b: number, c: number) => void;
    readonly __wbindgen_exn_store: (a: number) => void;
    readonly __externref_table_alloc: () => number;
    readonly __wbindgen_externrefs: WebAssembly.Table;
    readonly __externref_table_dealloc: (a: number) => void;
    readonly __wbindgen_start: () => void;
}

export type SyncInitInput = BufferSource | WebAssembly.Module;

/**
 * Instantiates the given `module`, which can either be bytes or
 * a precompiled `WebAssembly.Module`.
 *
 * @param {{ module: SyncInitInput }} module - Passing `SyncInitInput` directly is deprecated.
 *
 * @returns {InitOutput}
 */
export function initSync(module: { module: SyncInitInput } | SyncInitInput): InitOutput;

/**
 * If `module_or_path` is {RequestInfo} or {URL}, makes a request and
 * for everything else, calls `WebAssembly.instantiate` directly.
 *
 * @param {{ module_or_path: InitInput | Promise<InitInput> }} module_or_path - Passing `InitInput` directly is deprecated.
 *
 * @returns {Promise<InitOutput>}
 */
export default function __wbg_init (module_or_path?: { module_or_path: InitInput | Promise<InitInput> } | InitInput | Promise<InitInput>): Promise<InitOutput>;
