# Requirements: Mechanism core

## Introduction

The mechanism core is the single representation and the single solver used everywhere in Orrery. It defines the mechanism graph schema, and a Rust kinematics engine that assembles, simulates, analyzes, and fits mechanisms. The same compiled solver runs in the browser (WebAssembly in a Web Worker) and in the engine (Python bindings). The schema supports planar and spatial mechanisms from the first version so later specs do not require migration.

## Glossary

- **Mechanism graph**: bodies (nodes) connected by joints (edges), plus drivers, planes, scale, and provenance.
- **Body**: a rigid part, or a compliant part, with a local frame and named local points.
- **Joint**: a constraint between two bodies.
- **Driver**: an input that sets a joint coordinate over time (for example a crank angle).
- **Assembly**: the body poses that satisfy all joint constraints for given driver values.
- **Branch**: one of several assemblies that satisfy the same driver values.
- **Mobility**: the number of independent degrees of freedom.
- **Fit**: estimating geometry and driver values from observed point trajectories.

## Requirements

### Requirement 1: Mechanism graph schema

**User Story:** As a developer, I want one versioned schema for mechanisms, so that every component exchanges the same data.

#### Acceptance Criteria

1. THE schema SHALL be defined in Zod 4 in `packages/schema` and SHALL carry a `schemaVersion`.
2. THE schema SHALL represent bodies, joints, drivers, planes, scale, and provenance, with stable string IDs for every element.
3. THE schema SHALL record, for every body and joint, a status of `observed`, `inferred`, `user`, or `candidate`, and a confidence between 0 and 1.
4. THE schema SHALL record parameter uncertainty as standard deviations for each fitted numeric parameter.
5. THE schema SHALL store all geometry in SI units and SHALL record how scale was established: `user_measurement`, `reference_object`, `intrinsics`, or `unscaled`.
6. WHEN the schema version changes, THE package SHALL provide a migration function from each earlier version.

### Requirement 2: Cross-language types and validation

**User Story:** As a developer, I want generated types in TypeScript, Rust, and Python, so that the three languages cannot drift.

#### Acceptance Criteria

1. THE build SHALL emit JSON Schema from the Zod schema and generate Rust types and Python Pydantic models from it.
2. THE repository SHALL contain golden mechanism files covering every body kind and joint kind.
3. WHEN tests run, EACH language SHALL parse every golden file, and re-serialize it to a document that is semantically equal to the original.
4. THE validator SHALL reject graphs with dangling references, duplicate IDs, joints connecting a body to itself, or more than one ground body.

### Requirement 3: Body and joint library

**User Story:** As a restorer, I want the model to represent the parts real machines use, so that reconstructions are not limited to pin-jointed linkages.

#### Acceptance Criteria

1. THE schema and solver SHALL support body kinds `ground`, `link`, `slider_block`, `gear`, `cam`, `pulley`, and `compliant`.
2. THE schema and solver SHALL support planar joints `revolute`, `prismatic`, `pin_in_slot`, `gear_mesh` (external and internal, including rack and pinion), `belt` (open and crossed), `cam_follower` (knife, roller, and flat-faced followers), and `spring` (linear stiffness and free length).
3. THE schema and solver SHALL support spatial joints `spherical`, `universal`, `cylindrical`, and `revolute` and `prismatic` with arbitrary 3D axes.
4. THE schema SHALL support planar subsystems: groups of bodies constrained to a plane embedded in 3D, connected to other subsystems by spatial joints.
5. THE cam body SHALL store its profile as a periodic radial function with Fourier coefficients and SHALL support conversion to a polyline at a requested tolerance.
6. THE pin-in-slot joint SHALL store the slot as a curve in the slot body's frame (line segment, circular arc, or cubic B-spline).

### Requirement 4: Assembly

**User Story:** As a user, I want the solver to place every part correctly for any crank position, so that the simulation reflects the real machine.

#### Acceptance Criteria

1. WHEN given a mechanism and driver values, THE solver SHALL return body poses whose joint constraint residuals are below 1e-9 meters (or radians) or SHALL return a typed failure.
2. WHEN given a previous assembly as a seed, THE solver SHALL return the assembly on the same branch.
3. WHEN constraints cannot be satisfied, THE solver SHALL return `AssemblyFailed` with the joints whose residuals remain largest.
4. THE solver SHALL treat springs as energy terms and SHALL return the minimum-energy assembly among compliant degrees of freedom.

### Requirement 5: Cycle simulation and singularities

**User Story:** As a user, I want to turn the crank through a full cycle and see where the mechanism locks or changes behavior, so that I understand failure points.

#### Acceptance Criteria

1. WHEN asked to simulate over a driver range with a step, THE solver SHALL return poses and world trajectories of every named point for each step.
2. THE solver SHALL use continuation (seeding each step from the previous) and SHALL adapt the step size near singularities.
3. WHEN the constraint Jacobian loses rank during simulation, THE solver SHALL report a singularity event with the driver value, kind (`dead_center`, `lockup`, `bifurcation`), and the joints involved.
4. WHEN the mechanism cannot complete the requested range, THE solver SHALL report the reachable sub-ranges.
5. THE solver SHALL compute velocities and accelerations of every named point from the constraint Jacobian.

### Requirement 6: Mobility analysis

**User Story:** As a user, I want to know how many independent motions the mechanism has, so that missing or redundant parts are obvious.

#### Acceptance Criteria

1. THE solver SHALL compute mobility by the Grübler–Kutzbach formula and by numerical rank of the constraint Jacobian at a given assembly.
2. WHEN the two mobility values differ, THE solver SHALL report the redundant constraints identified by rank analysis.
3. THE solver SHALL report the unconstrained degrees of freedom as motion directions on the affected bodies.

### Requirement 7: Fitting

**User Story:** As the engine, I want to fit mechanism geometry and per-frame driver values to tracked points, so that a model can be reconstructed from video.

#### Acceptance Criteria

1. THE fitter SHALL accept a mechanism topology with initial parameter guesses, per-frame observations of named points in a given frame (image or stabilized), observation weights, and visibility.
2. THE fitter SHALL estimate geometry parameters, per-frame driver values, and optional camera parameters (planar homography or full projection).
3. THE fitter SHALL keep joint constraints exactly satisfied at every frame and SHALL minimize a robust (Huber or Cauchy) reprojection error.
4. THE fitter SHALL exploit the per-frame block structure using sparse linear algebra so that a 600-frame, 20-body problem fits in under 5 seconds on one CPU core.
5. THE fitter SHALL return parameter standard deviations from the approximate covariance, the final residual statistics, and per-observation residuals.
6. THE fitter SHALL support holding any parameter fixed and setting priors on any parameter.

### Requirement 8: Plausibility and collision metrics

**User Story:** As the resurrection engine, I want physical plausibility measures, so that impossible repairs rank low.

#### Acceptance Criteria

1. THE solver SHALL compute, over a simulated cycle, the minimum transmission angle at each revolute joint pair that forms a four-bar loop.
2. THE solver SHALL classify four-bar loops by the Grashof condition.
3. THE solver SHALL detect collisions between body outlines in the same plane, using body thickness for subsystems in parallel planes, and report the driver ranges where they occur.
4. THE solver SHALL report joint reaction direction changes and maximum link-length to width ratios as fabrication risk indicators.

### Requirement 9: WebAssembly bindings

**User Story:** As a user editing in the browser, I want the simulation to respond instantly, so that editing feels like handling a physical model.

#### Acceptance Criteria

1. THE solver SHALL compile to WebAssembly and run in a dedicated Web Worker.
2. THE worker client SHALL expose a typed Promise API and SHALL transfer trajectory data as transferable typed arrays.
3. WHEN a user drags a joint in a 20-body mechanism, THE solver SHALL re-solve one assembly in under 2 ms and a 360-step cycle in under 50 ms on a mid-range laptop.
4. THE worker SHALL cancel superseded requests so that only the latest edit is solved.

### Requirement 10: Python bindings

**User Story:** As an engine developer, I want the solver in Python with NumPy arrays, so that the vision pipeline uses the same solver as the browser.

#### Acceptance Criteria

1. THE solver SHALL be importable in Python as `orrery_kinematics`, built with maturin, with type stubs.
2. THE Python API SHALL accept and return NumPy arrays without copying where layouts allow.
3. THE Python API SHALL release the GIL during solving and fitting.

### Requirement 11: Determinism and parity

**User Story:** As a developer, I want the native and WebAssembly builds to agree, so that what the engine predicts is what the user sees.

#### Acceptance Criteria

1. FOR every golden mechanism and fixed inputs, THE native and WebAssembly builds SHALL produce poses that agree within 1e-9.
2. THE solver SHALL be deterministic for identical inputs within one build.
