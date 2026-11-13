/**
 * The WebAssembly solver and its worker protocol, in Node: the module is loaded from the built
 * `pkg/`, and the client and host talk over a real `MessageChannel` as they do across a worker.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { MessageChannel } from "node:worker_threads";
import type { Mechanism } from "@orrery/schema";
import { beforeAll, describe, expect, it } from "vitest";
import { fit, initSync, Solver } from "../pkg/kinematics.js";
import { Cancelled, SolverClient, SolverError } from "../src/client.ts";
import { serve } from "../src/host.ts";
import type { Port } from "../src/protocol.ts";

const golden = (name: string): Mechanism =>
  JSON.parse(
    readFileSync(join(import.meta.dirname, "../../../fixtures/golden/mechanism", name), "utf8"),
  );

beforeAll(() => {
  initSync({ module: readFileSync(join(import.meta.dirname, "../pkg/kinematics_bg.wasm")) });
});

function connect() {
  const { port1, port2 } = new MessageChannel();
  serve(port2 as unknown as Port, { Solver, fit });
  port1.start();
  port2.start();
  return { client: new SolverClient(port1 as unknown as Port), close: () => port1.close() };
}

describe("WebAssembly solver", () => {
  it("assembles the golden four-bar where the closed form puts it", () => {
    const solver = new Solver(JSON.stringify(golden("four-bar-crank-rocker.json")));
    const names: [string, string][] = solver.pointNames();
    const state = solver.assemble([0.7]);
    expect(state).toHaveLength(solver.stateSize());
    const points = solver.pointPositions(state);
    const b = names.findIndex(([body, point]) => body === "crank" && point === "b");
    expect(points[3 * b]).toBeCloseTo(0.1 * Math.cos(0.7), 12);
    expect(points[3 * b + 1]).toBeCloseTo(0.1 * Math.sin(0.7), 12);
    solver.free();
  });

  it("throws typed errors as plain objects", () => {
    expect(() => new Solver("{}")).toThrow(
      expect.objectContaining({ kind: "invalidGraph" }) as unknown as Error,
    );
    const broken = golden("four-bar-crank-rocker.json");
    const ground = broken.bodies[0];
    if (ground?.points[1]) ground.points[1].local.x = 0.8;
    const solver = new Solver(JSON.stringify(broken));
    try {
      solver.assemble([0.3]);
      expect.unreachable();
    } catch (error) {
      expect(error).toMatchObject({
        kind: "assemblyFailed",
        detail: { worstJoints: expect.any(Array) },
      });
    }
  });
});

describe("solver worker protocol", () => {
  it("opens, assembles, simulates, and reports mobility through the client", async () => {
    const { client, close } = connect();
    const handle = await client.open(golden("four-bar-crank-rocker.json"));
    expect(handle.stateSize).toBe(9);
    expect(handle.driverCount).toBe(1);
    const state = await client.assemble(handle, [0.4]);
    expect(state).toBeInstanceOf(Float64Array);
    const sim = await client.simulate(handle, {
      driver: 0,
      drive: [0],
      start: 0,
      end: 2 * Math.PI,
      step: Math.PI / 36,
    });
    expect(sim.drive).toHaveLength(73);
    expect(sim.states).toHaveLength(73 * 9);
    expect(sim.points).toHaveLength(73 * handle.pointNames.length * 3);
    expect(sim.reachable).toEqual([[0, 2 * Math.PI]]);
    expect(sim.singularities.filter((s) => s.kind === "lockup")).toHaveLength(2);
    const mobility = await client.mobility(handle, state, [0.4]);
    expect(mobility).toMatchObject({ grubler: 1, numerical: 1, redundant: [], freeMotions: [] });
    const plausibility = await client.plausibility(handle, {
      driver: 0,
      drive: [0],
      start: 0,
      end: 6.28,
      step: 0.1,
    });
    expect(plausibility.loops[0]?.grashof).toBe("crank_rocker");
    await client.close(handle);
    close();
  });

  it("rejects with typed errors", async () => {
    const { client, close } = connect();
    const bad = golden("four-bar-crank-rocker.json");
    bad.joints[1] = { ...bad.joints[1], bodyB: "missing" } as Mechanism["joints"][number];
    await expect(client.open(bad)).rejects.toSatisfy(
      (e: unknown) => e instanceof SolverError && e.detail.kind === "invalidGraph",
    );
    const handle = await client.open(golden("four-bar-crank-rocker.json"));
    await expect(client.assemble(handle, [])).rejects.toSatisfy(
      (e: unknown) => e instanceof SolverError && e.detail.kind === "driverCount",
    );
    close();
  });

  it("runs only the latest waiting request on a channel", async () => {
    const { client, close } = connect();
    const handle = await client.open(golden("four-bar-crank-rocker.json"));
    const drags = [0.1, 0.2, 0.3, 0.4, 0.5].map((angle) =>
      client.assemble(handle, [angle], undefined, "drag"),
    );
    // A request on another channel is not superseded.
    const other = client.assemble(handle, [1.0], undefined, "preview");
    const settled = await Promise.allSettled(drags);
    expect(
      settled.slice(0, 4).every((s) => s.status === "rejected" && s.reason instanceof Cancelled),
    ).toBe(true);
    const last = settled[4];
    expect(last?.status).toBe("fulfilled");
    const positions = await client.pointPositions(
      handle,
      (last as PromiseFulfilledResult<Float64Array>).value,
    );
    const b = handle.pointNames.findIndex(([body, point]) => body === "crank" && point === "b");
    expect(positions[3 * b]).toBeCloseTo(0.1 * Math.cos(0.5), 12);
    await expect(other).resolves.toBeInstanceOf(Float64Array);
    close();
  });

  it("fits through the worker", async () => {
    const { client, close } = connect();
    const mechanism = golden("four-bar-crank-rocker.json");
    const solver = new Solver(JSON.stringify(mechanism));
    const names: [string, string][] = solver.pointNames();
    const frames = Array.from({ length: 20 }, (_, t) => 0.3 + (5 * t) / 20);
    let seed: Float64Array | undefined;
    const observations = frames.flatMap((angle, frame) => {
      seed = solver.assemble([angle], seed ?? null);
      const p = solver.pointPositions(seed);
      return (["b", "trace", "tip"] as const).map((point) => {
        const body = point === "b" ? "crank" : point === "trace" ? "coupler" : "rocker";
        const i = names.findIndex(([n, q]) => n === body && q === point);
        return { frame, body, point, position: [p[3 * i], p[3 * i + 1]], weight: 1 };
      });
    });
    const start = structuredClone(mechanism);
    const coupler = start.bodies[2];
    if (coupler?.points[1]) coupler.points[1].local.x = 0.26;
    const result = (await client.fit({
      mechanism: start,
      parameters: [{ path: "bodies.coupler.points.c.local.x" }],
      drive: frames.map((a) => [a]),
      observations,
      camera: { type: "plane", plane: "plane-main" },
      loss: { type: "squared" },
      maxIterations: 30,
    })) as { values: number[]; rms: number };
    expect(result.values[0]).toBeCloseTo(0.25, 9);
    close();
  });
});
