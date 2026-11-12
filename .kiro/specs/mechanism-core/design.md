# Design: Mechanism core

## Overview

```
packages/schema (Zod) ──► JSON Schema ──► crates/kinematics (typify types)
                                     └──► services/engine, tools/lab (Pydantic)
crates/kinematics ──► crates/kinematics-wasm ──► packages/kinematics-wasm (Web Worker client)
                  └──► crates/kinematics-py  ──► orrery_kinematics (Python wheel)
```

The solver uses maximal coordinates: every body has a pose, and every joint contributes residual equations. This handles closed loops, mixed joint types, and spatial subsystems in one formulation. It also gives the block-sparse structure the fitter needs.

## Schema (`packages/schema`)

```ts
Mechanism = {
  schemaVersion: 1,
  id: string, name: string,
  scale: { source: "user_measurement" | "reference_object" | "intrinsics" | "unscaled", metersPerUnit: number, sigma?: number },
  planes: Plane[],          // Plane = { id, originWorld: Vec3, normalWorld: Vec3, xAxisWorld: Vec3 }
  bodies: Body[],
  joints: Joint[],
  drivers: Driver[],
  provenance: { createdBy: "engine" | "user" | "lab", analysisId?: string, footageIds: string[], engineVersion?: string },
}
Body = {
  id, label, kind: "ground" | "link" | "slider_block" | "gear" | "cam" | "pulley" | "compliant",
  planeId: string | null,            // null = spatial body
  points: { id: string, local: Vec3, role: "joint_anchor" | "tracked" | "output" | "hole" }[],
  outline?: { polygonLocal: Vec2[], thickness: number },
  gear?: { teeth: number, module: number, internal: boolean },
  cam?: { baseRadius: number, fourier: { a: number[], b: number[] } },
  pulley?: { radius: number },
  status: Status, confidence: number,
}
Joint = { id, bodyA, bodyB, status, confidence } & (
  | { kind: "revolute", anchorA: PointRef, anchorB: PointRef, axisLocalA?: Vec3 }
  | { kind: "prismatic", anchorA, anchorB, axisLocalA: Vec3, limits?: [number, number] }
  | { kind: "pin_in_slot", pin: PointRef, slot: Curve }
  | { kind: "gear_mesh", ratio: number, phase: number }
  | { kind: "belt", ratio: number, crossed: boolean }
  | { kind: "cam_follower", follower: "knife" | "roller" | "flat", followerPoint: PointRef, rollerRadius?: number }
  | { kind: "spring", anchorA, anchorB, stiffness: number, freeLength: number }
  | { kind: "spherical" | "universal" | "cylindrical", anchorA, anchorB, axesLocal?: [Vec3, Vec3] }
)
Driver = { id, jointId, coordinate: "angle" | "displacement",
  profile: { type: "constant_rate", rate: number, phase0: number } | { type: "samples", t: number[], q: number[] } }
Uncertainty = Record<ParameterPath, number>   // stored alongside, e.g. "bodies.crank.points.p1.local.x"
```

Validation refinements (Zod `superRefine`): reference integrity, single ground, planar joints only between bodies in the same plane, gear joints only between gear bodies, finite numbers.

## Solver (`crates/kinematics`)

### State

- Planar body pose: `(x, y, θ)` in its plane. Spatial body pose: position plus unit quaternion, with a 3-parameter local update during iteration.
- The ground body is fixed and removed from the unknowns.

### Constraints

Each joint kind implements `trait Constraint { fn residual(&self, q, out); fn jacobian(&self, q, triplets); fn dim(&self) -> usize }`.

| Joint | Residual |
|---|---|
| revolute (planar) | anchor A in world − anchor B in world (2) |
| prismatic (planar) | perpendicular offset of B's anchor from A's axis (1), relative rotation (1) |
| pin-in-slot | signed distance of pin from slot curve, with the curve parameter as an extra unknown (1 + 1 unknown) |
| gear mesh | θ_B − θ_A·(−ratio) − phase, relative to the carrier (1). Center distance is a separate revolute/ground relation |
| belt | as gear with sign from `crossed` (1) |
| cam follower | contact of follower point with the cam profile offset by roller radius, with cam angle parameter (1 + 1 unknown) |
| driver | joint coordinate − driver value (1) |
| spatial | standard formulations: spherical (3), universal (4), cylindrical (4) |

Springs do not add residuals. They add energy `½k(L − L0)²`.

### Assembly

- Solve `Φ(q) = 0` with Levenberg–Marquardt on the residual vector. With springs, minimize energy subject to the constraints using a projected Newton step in the constraint null space.
- Linear solves use `faer` sparse QR for the constraint Jacobian. A small dense path handles mechanisms with fewer than 30 unknowns.
- Branch continuity: seed from the previous pose. Reject a step if any body rotates more than a bound or the solution jumps, then halve the step.

### Simulation and singularities

- Continuation over the driver range with adaptive steps.
- At each step, compute the singular values of the reduced Jacobian. When the smallest falls below a threshold, refine the location by bisection and classify:
  - `dead_center`: the driver Jacobian column loses influence (input singularity).
  - `lockup`: the output loses mobility.
  - `bifurcation`: the null space dimension increases.
- Velocities: solve `Φ_q q̇ = −Φ_t`. Accelerations from the second-order term using automatic differentiation of residuals (forward-mode dual numbers implemented in the crate).

### Mobility

- Grübler–Kutzbach from body and joint counts and joint freedoms.
- Numerical: `nq − rank(Φ_q)` with rank from SVD with a tolerance relative to the largest singular value. Redundant constraints are rows that rank-revealing QR places in the dependent set.

### Fitter

Unknowns: geometry parameters θ (anchor locals, gear phase, cam coefficients, slot curves), per-frame driver values `d_t`, optional camera parameters `c` (per-frame homography or a static projection with per-frame pose).

Objective:

```
min_{θ, d, c}  Σ_t Σ_i w_ti · ρ( || π(c_t, p_i(q_t(θ, d_t))) − z_ti || )  +  priors(θ)
subject to     Φ(q_t; θ, d_t) = 0   for every t
```

- `q_t` is eliminated by solving assembly at each frame (implicit function). The derivative of `q_t` with respect to `(θ, d_t)` comes from `−Φ_q⁻¹ Φ_(θ,d)`.
- The normal equations have an arrow structure: per-frame blocks for `d_t` and `c_t`, plus a dense block for `θ`. Solve with the Schur complement on `θ`, as in bundle adjustment.
- Robust loss via iteratively reweighted least squares.
- Covariance: inverse of the reduced normal matrix at the solution, scaled by the residual variance. Reported as per-parameter standard deviations.

### Plausibility

- Transmission angle per four-bar loop found by cycle detection in the graph.
- Grashof classification from the four link lengths.
- Collisions: `parry2d` shapes from outlines per plane, swept over the cycle with conservative advancement between steps.

## WebAssembly (`crates/kinematics-wasm`, `packages/kinematics-wasm`)

- `wasm-bindgen` exports: `Solver.new(graphJson)`, `assemble(driverValues, seed?)`, `simulate(range, step)`, `mobility()`, `plausibility(range)`, `fit(problem)`.
- A Web Worker hosts one `Solver` per open mechanism. A `SolverClient` class wraps `postMessage` with request IDs, cancellation tokens (latest-wins per channel), and transferable `Float64Array` buffers.
- Built with `wasm-pack --target web`, SIMD enabled, `opt-level = 3`, `lto = true`.

## Python (`crates/kinematics-py`)

- PyO3 classes mirroring the WASM API. NumPy via the `numpy` crate. `py.allow_threads` around solve and fit. Type stubs generated with `pyo3-stub-gen`.

## Error handling

- `SolverError` enum: `InvalidGraph`, `AssemblyFailed { worst_joints }`, `RangeIncomplete { reachable }`, `FitDiverged { iteration, cost }`, `Cancelled`. Mapped to typed errors in TS and Python.

## Correctness properties

1. *For any* valid generated mechanism and reachable driver value, assembly residuals are below 1e-9. **Validates: 4.1**
2. *For any* body and any two of its points, their world distance is constant across a simulated cycle. **Validates: 4.1, 5.1**
3. *For any* simulation step where no singularity is reported, the pose change is bounded by a Lipschitz constant times the driver step. **Validates: 4.2, 5.2**
4. *For any* mechanism without special geometry, numerical mobility equals Grübler mobility. For parallelogram linkages, numerical mobility is 1 and the redundant constraint is reported. **Validates: 6.1, 6.2**
5. *For any* mechanism, driver sweep, and Gaussian observation noise σ (with no outliers), fitting from perturbed initial guesses recovers link lengths within 3σ times the reported standard deviation. **Validates: 7.2, 7.5**
6. *For any* observation set with up to 20% outliers, the robust fit's error stays within 2× the outlier-free error. **Validates: 7.3**
7. *For any* golden mechanism, parse → serialize → parse is the identity in TypeScript, Rust, and Python. **Validates: 2.3**
8. *For any* golden mechanism and inputs, native and WebAssembly poses agree within 1e-9. **Validates: 11.1**
9. *For any* gear pair with ratio r, the output angle equals −r times the input angle (external) or r times (internal) at every step. **Validates: 3.2**
10. *For any* graph with a dangling reference, duplicate ID, or self-joint, validation fails in every language. **Validates: 2.4**

## Testing strategy

- `proptest` generators produce random valid mechanisms per family (four-bar, slider-crank, six-bar, geared, cam, spatial RSSR), using the same family definitions as the synthetic lab.
- `criterion` benchmarks enforce the performance targets in 7.4 and 9.3. CI fails on regressions above 15%.
- Parity tests run the WebAssembly build in Node and compare to native on golden fixtures.
- Python tests use hypothesis with the same property definitions.
