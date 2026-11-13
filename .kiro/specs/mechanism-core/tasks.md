# Tasks: Mechanism core

- [ ] 1. Schema and code generation
  - [x] 1.1 Implement the Zod schema in `packages/schema` with refinements, version field, and migration registry.
    - _Requirements: 1.1–1.6, 2.4_
  - [x] 1.2 Emit JSON Schema, generate Rust types with `typify` and Pydantic models with `datamodel-code-generator`. Add to `pnpm codegen` and the stale check.
    - _Requirements: 2.1_
    - `pnpm codegen` emits `schema/mechanism.json` (draft-07, the form typify reads tuples in), then `cargo typify` writes `crates/kinematics/src/generated/mechanism.rs` (tagged enums, `BTreeMap`, rustfmt-formatted) and `datamodel-codegen` writes `services/engine/src/orrery_engine/generated/mechanism.py`. All three are in the stale check. `cargo-typify` 0.8.0 is pinned in the toolbox. The cross-reference rules are not expressible in JSON Schema: Zod's refinement and `kinematics::validate` implement them, with the same messages.
  - [ ] 1.3 Author golden fixtures in `fixtures/golden/` covering every body and joint kind, including a spatial RSSR and a two-plane subsystem example. Add round-trip tests in all three languages (property 7) and invalid-graph tests (property 10).
    - _Requirements: 2.2, 2.3, 2.4_
    - Done: seven files in `fixtures/golden/mechanism` cover every body kind, joint kind, follower, slot curve, driver profile, external and internal meshes, open and crossed belts, a spatial RSSR, and two planar subsystems in perpendicular planes; eight files in `invalid/` each break one rule. Round trips pass in TypeScript, Rust, and Python, and invalid graphs fail in TypeScript and Rust. Remaining: the Python invalid-graph test, which calls `kinematics::validate` through `kinematics-py` (6.3) so the rules are not written a third time.

- [ ] 2. Planar solver
  - [ ] 2.1 Implement state layout, the `Constraint` trait, and revolute, prismatic, and driver constraints with analytic Jacobians.
    - _Requirements: 3.2, 4.1_
  - [ ] 2.2 Implement Levenberg–Marquardt assembly with `faer` sparse and dense paths, seeded branch continuity, and `AssemblyFailed` diagnostics.
    - _Requirements: 4.1, 4.2, 4.3_
  - [ ] 2.3 Implement pin-in-slot, gear mesh (external, internal, rack and pinion), belt, and cam-follower constraints, plus cam Fourier profiles and slot curves.
    - _Requirements: 3.1, 3.2, 3.5, 3.6_
  - [ ] 2.4 Implement spring energy terms and constrained energy minimization.
    - _Requirements: 4.4_
  - [ ] 2.5 Property tests 1, 2, and 9 with `proptest` mechanism generators.
    - _Requirements: 4.1, 3.2_

- [ ] 3. Simulation and analysis
  - [ ] 3.1 Implement continuation with adaptive steps, reachable sub-ranges, and singularity detection and classification.
    - _Requirements: 5.1–5.4_
  - [ ] 3.2 Implement velocities and accelerations with forward-mode dual numbers.
    - _Requirements: 5.5_
  - [ ] 3.3 Implement Grübler and numerical mobility with redundant-constraint and free-motion reporting. Property test 4.
    - _Requirements: 6.1–6.3_
  - [ ] 3.4 Implement transmission angle, Grashof classification, swept collision detection with `parry2d`, and fabrication risk indicators.
    - _Requirements: 8.1–8.4_
  - [ ] 3.5 Property test 3 (continuity).
    - _Requirements: 4.2, 5.2_

- [ ] 4. Spatial support
  - [ ] 4.1 Implement spatial body poses with quaternions and spherical, universal, cylindrical, and 3D-axis revolute and prismatic constraints.
    - _Requirements: 3.3_
  - [ ] 4.2 Implement planar subsystems embedded in planes and connected by spatial joints, with `parry3d` collisions between subsystems.
    - _Requirements: 3.4, 8.3_

- [ ] 5. Fitter
  - [ ] 5.1 Implement the implicit-function fitter with Schur complement on geometry parameters, robust IRLS, fixed parameters, and priors.
    - _Requirements: 7.1, 7.2, 7.3, 7.6_
  - [ ] 5.2 Implement planar homography and full projection camera models in the fitter.
    - _Requirements: 7.2_
  - [ ] 5.3 Implement covariance and per-observation residual reporting.
    - _Requirements: 7.5_
  - [ ] 5.4 Property tests 5 and 6. Criterion benchmark for the 600-frame, 20-body target.
    - _Requirements: 7.3, 7.4, 7.5_

- [ ] 6. Bindings
  - [ ] 6.1 Build `crates/kinematics-wasm` and `packages/kinematics-wasm` with the Web Worker host, typed `SolverClient`, latest-wins cancellation, and transferable buffers.
    - _Requirements: 9.1, 9.2, 9.4_
  - [ ] 6.2 Browser performance test in Playwright measuring drag re-solve and cycle simulation against the targets.
    - _Requirements: 9.3_
  - [ ] 6.3 Build `crates/kinematics-py` with maturin, NumPy I/O, GIL release, and generated stubs.
    - _Requirements: 10.1, 10.2, 10.3_
  - [ ] 6.4 Native versus WebAssembly parity tests on golden fixtures and determinism tests (property 8).
    - _Requirements: 11.1, 11.2_
