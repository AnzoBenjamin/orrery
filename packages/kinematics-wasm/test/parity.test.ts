/**
 * Native versus WebAssembly parity (mechanism-core requirement 11, property 8). The native results
 * in `fixtures/golden/parity` are written and checked by `crates/kinematics/tests/parity.rs`; this
 * test runs the same inputs through the built WebAssembly module and compares within 1e-9.
 * Point positions are compared for every mechanism. States are compared only where the joints and
 * drivers leave nothing free: along a free motion (a rod spinning about the line through its ball
 * joints, which moves no point) the state is wherever the iterations left it.
 * It also checks that the WebAssembly build is deterministic: the same call twice gives
 * bit-identical output (requirement 11.2).
 */
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { beforeAll, describe, expect, it } from "vitest";
import { initSync, fit as runFit, Solver } from "../pkg/kinematics.js";

const fixtures = join(import.meta.dirname, "../../../fixtures/golden");
const TOLERANCE = 1e-9;

type Sweep = { driver: number; start: number; end: number; step: number };

type MechanismCase = {
  mechanism: string;
  inputs: { drive: number[]; sweep: Sweep };
  assembled: number[];
  points: (number | null)[];
  simulation: {
    drive: number[];
    states: number[];
    points: (number | null)[];
    reachable: [number, number][];
    singularities: { drive: number; kind: string; joints: string[] }[];
  };
  mobility: { grubler: number; numerical: number; redundant: unknown[]; freeMotions: number };
};

type FitCase = {
  problem: unknown;
  result: {
    values: number[];
    sigma: number[];
    drive: number[][];
    poses: number[][];
    iterations: number;
  };
};

type SimulationOut = {
  drive: Float64Array;
  states: Float64Array;
  points: Float64Array;
  reachable: [number, number][];
  singularities: { drive: number; kind: string; joints: string[] }[];
};

const read = <T>(name: string): T =>
  JSON.parse(readFileSync(join(fixtures, "parity", name), "utf8")) as T;

/** The native side writes NaN (a point it could not place) as JSON null. */
const nativeNumbers = (values: (number | null)[]): number[] => values.map((v) => v ?? Number.NaN);

/** The largest elementwise difference, failing on a length mismatch or a NaN on one side only. */
function maxDifference(wasm: ArrayLike<number>, native: ArrayLike<number>, what: string): number {
  expect(wasm.length, `${what}: length`).toBe(native.length);
  let worst = 0;
  for (let i = 0; i < native.length; i++) {
    const a = wasm[i] ?? Number.NaN;
    const b = native[i] ?? Number.NaN;
    if (Number.isNaN(a) || Number.isNaN(b)) {
      expect(Number.isNaN(a), `${what}[${i}]: ${a} vs ${b}`).toBe(Number.isNaN(b));
      continue;
    }
    worst = Math.max(worst, Math.abs(a - b));
  }
  return worst;
}

function expectClose(wasm: ArrayLike<number>, native: ArrayLike<number>, what: string) {
  expect(maxDifference(wasm, native, what), what).toBeLessThanOrEqual(TOLERANCE);
}

const mechanismCases = readdirSync(join(fixtures, "parity"))
  .filter((name) => name !== "fit-four-bar.json")
  .sort();

beforeAll(() => {
  initSync({ module: readFileSync(join(import.meta.dirname, "../pkg/kinematics_bg.wasm")) });
});

describe("native and WebAssembly parity", () => {
  it("covers every golden mechanism", () => {
    const goldens = readdirSync(join(fixtures, "mechanism"))
      .filter((name) => name.endsWith(".json"))
      .sort();
    expect(mechanismCases).toEqual(goldens);
  });

  it.each(mechanismCases)("%s agrees within 1e-9", (name) => {
    const native = read<MechanismCase>(name);
    const solver = new Solver(readFileSync(join(fixtures, "mechanism", native.mechanism), "utf8"));
    try {
      const { drive, sweep } = native.inputs;
      const assembled = solver.assemble(drive);
      const determined = native.mobility.freeMotions === 0;
      if (determined) expectClose(assembled, native.assembled, "assembled");
      expectClose(solver.pointPositions(assembled), nativeNumbers(native.points), "points");

      const sim = solver.simulate(
        sweep.driver,
        drive,
        sweep.start,
        sweep.end,
        sweep.step,
        assembled,
      ) as unknown as SimulationOut;
      expectClose(sim.drive, native.simulation.drive, "simulation.drive");
      expect(sim.states).toHaveLength(native.simulation.states.length);
      if (determined) expectClose(sim.states, native.simulation.states, "simulation.states");
      expectClose(sim.points, nativeNumbers(native.simulation.points), "simulation.points");
      expectClose(sim.reachable.flat(), native.simulation.reachable.flat(), "simulation.reachable");
      expect(sim.singularities.map((s) => [s.kind, s.joints])).toEqual(
        native.simulation.singularities.map((s) => [s.kind, s.joints]),
      );
      expectClose(
        sim.singularities.map((s) => s.drive),
        native.simulation.singularities.map((s) => s.drive),
        "singularity drive",
      );

      const mobility = solver.mobility(assembled, drive) as {
        grubler: number;
        numerical: number;
        redundant: unknown[];
        freeMotions: unknown[];
      };
      expect({
        grubler: mobility.grubler,
        numerical: mobility.numerical,
        redundant: mobility.redundant,
        freeMotions: mobility.freeMotions.length,
      }).toEqual(native.mobility);
    } finally {
      solver.free();
    }
  });

  it("fits the four-bar to the same values, drives, and poses", () => {
    const native = read<FitCase>("fit-four-bar.json");
    const result = runFit(JSON.stringify(native.problem)) as FitCase["result"];
    expect(result.iterations).toBe(native.result.iterations);
    expectClose(result.values, native.result.values, "values");
    expectClose(result.sigma, native.result.sigma, "sigma");
    expectClose(result.drive.flat(), native.result.drive.flat(), "drive");
    expectClose(result.poses.flat(), native.result.poses.flat(), "poses");
  });
});

describe("WebAssembly determinism", () => {
  it("gives bit-identical results for identical inputs", () => {
    for (const name of mechanismCases) {
      const native = read<MechanismCase>(name);
      const text = readFileSync(join(fixtures, "mechanism", native.mechanism), "utf8");
      const { drive, sweep } = native.inputs;
      const run = () => {
        const solver = new Solver(text);
        try {
          const sim = solver.simulate(
            sweep.driver,
            drive,
            sweep.start,
            sweep.end,
            sweep.step,
          ) as unknown as SimulationOut;
          return [...sim.states, ...sim.points] as number[];
        } finally {
          solver.free();
        }
      };
      const first = run();
      const second = run();
      expect(first.length).toBe(second.length);
      expect(
        first.every((v, i) => Object.is(v, second[i])),
        name,
      ).toBe(true);
    }
    const problem = JSON.stringify(read<FitCase>("fit-four-bar.json").problem);
    expect(JSON.stringify(runFit(problem))).toBe(JSON.stringify(runFit(problem)));
  });
});
