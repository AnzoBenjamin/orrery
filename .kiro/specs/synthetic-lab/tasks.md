# Tasks: Synthetic lab

- [ ] 1. Lab package and families
  - [x] 1.1 Create `tools/lab` with Typer CLI, the `Family` protocol, parameter spaces, and feasibility checks using `orrery_kinematics`.
    - _Requirements: 1.2, 1.5_
    - `orrery-lab` (`version`, `families`, `sample`). A family's `build` draws every body in world coordinates at driver zero, so the drawn pose holds and fixes the branch, and returns the driver range (cyclic for cranks, rocking otherwise) and its breakable parts. Documents are checked by the Pydantic models generated from the shared JSON Schema (copied into the lab by `pnpm codegen`) and by the solver's validation. Feasibility sweeps outward from the drawn pose to both ends of the range: one unbroken reachable range, no dead center, no branch point unless the family allows it, no collisions, and a driven transmission angle (at the coupler-output joint) of at least the family minimum, 20° by default. Rejection sampling with one generator per seed. Property 1 runs under Hypothesis.
  - [x] 1.2 Implement linkage families: four-bar classes, slider-crank, inverted slider-crank, Scotch yoke, Watt and Stephenson six-bars, Chebyshev lambda, Peaucellier–Lipkin, pantograph, Jansen leg, Whitworth quick-return, flapping-wing automaton.
    - _Requirements: 1.1_
    - 18 families in `families/four_bar.py`, `sliders.py`, and `linkages.py`; pin-jointed ones are drawn from joint locations by `families/pinned.py`. Six-bar names follow McCarthy and Soh (Watt I, II; Stephenson I, II, III by where the extra dyad attaches). Each family has a behavior test against its namesake: Peaucellier–Lipkin's pen is straight to 1e-9, the pantograph copies its tracer at its ratio, the Scotch yoke is harmonic, the slider stays on its guide, the Whitworth ram returns faster than it cuts, the Jansen foot spends over a quarter of the turn on a flat stride (this caught the foot triangle's two sides swapped), and both wings rock.
  - [x] 1.3 Implement gear train, rack and pinion, belt drive, Geneva drive, cam-follower families, and the sewing-machine needle bar and take-up lever family.
    - _Requirements: 1.1_
    - `families/drives.py`: gear trains of two to four spur gears (the last optionally an internal ring), rack and pinion (rocking), belt drives with open and crossed belts, the Geneva drive over one indexing (the locking disk's contact between indexings is outside the schema, so a sample covers the engaged arc), knife, roller, and flat-faced cam followers on convex Fourier cams with a return spring, and the sewing machine (needle bar slider-crank plus take-up lever on the same crank pin). Tests check tooth and radius ratios, rack travel per radian, the closed-form Geneva motion, follower contact against the profile, and the needle bar's straight stroke. Feasibility now also rejects a sample the solver assembles anywhere but where it was drawn. Two solver gaps surfaced and were fixed in mechanism-core: rack and pinion was missing, and slot and cam parameters started from a grid, so drawn poses on curves were not recognized and could flip branch.
  - [x] 1.4 Implement spatial RSSR and multi-plane samples.
    - _Requirements: 1.1_
    - `families/spatial.py`: RSSR on skew axles (spatial bodies drawn in world coordinates), and `two-plane-cardan`, two crank-rockers in different planes joined by a double-Cardan shaft with a slip joint. Tests: RSSR links stay rigid and the rocker's ball turns in the plane of its axle; between parallel planes the in-phase Cardan pair turns the output exactly with the input, and a tilted rear plane makes it lead and lag within a turn. The drawn-pose check maps each planar body's plane coordinates to the world.
  - [ ] 1.5 Implement appearance generation (outlines, involute gears, holes, decorations) and the compound-machine composer. Property test 1.
    - _Requirements: 1.3, 1.4_

- [ ] 2. Breakage
  - [ ] 2.1 Implement part removal with hole points and ground-truth records. Property test 4.
    - _Requirements: 2.1, 2.3_
  - [ ] 2.2 Implement loose-part planar dynamics with gravity, friction, and ground contact. Property test 5.
    - _Requirements: 2.2_

- [ ] 3. Rendering
  - [ ] 3.1 Implement the Skia 2D renderer with procedural and CC0 materials, shadows, camera model with tilt and distortion, and clutter.
    - _Requirements: 3.1, 3.2, 3.3_
  - [ ] 3.2 Implement animated hand and tool occluders.
    - _Requirements: 3.4_
  - [ ] 3.3 Implement the Blender 3D renderer with RGB, depth, and instance passes and multiple camera paths.
    - _Requirements: 5.1, 5.2, 5.3_

- [ ] 4. Degradations
  - [ ] 4.1 Implement shake, motion blur, rolling shutter, noise, and exposure drift.
    - _Requirements: 4.1, 4.2_
  - [ ] 4.2 Implement encoding variants, VFR, and dropped frames.
    - _Requirements: 4.3_
  - [ ] 4.3 Implement the archival profile and record all degradation parameters.
    - _Requirements: 4.4, 4.5_

- [ ] 5. Ground truth and suites
  - [ ] 5.1 Implement the export format (MP4, `truth.json`, Arrow, masks, depth). Property test 3.
    - _Requirements: 6.1, 6.2_
  - [ ] 5.2 Implement suite manifests, hashing, deterministic generation, and object-storage caching. Write `smoke`, `core`, and `full` manifests. Property test 2.
    - _Requirements: 7.1–7.4_

- [ ] 6. Fixtures for other specs
  - [ ] 6.1 Generate and commit short end-to-end fixture clips with ground truth to `e2e/fixtures` (clean four-bar, broken flapping wing, repaired flapping wing, phone-profile slider-crank).
    - _Requirements: 6.3_

- [ ] 7. Evaluation and gate
  - [ ] 7.1 Implement the harness that runs clips through the engine job API and computes all stage metrics.
    - _Requirements: 8.1, 8.2_
  - [ ] 7.2 Implement breakdowns by family, profile, and tier, and the versioned report format in `packages/engine-contract`.
    - _Requirements: 8.3, 8.6_
  - [ ] 7.2a Run the engine under the reference VPS resource profile in the harness, and add tracker-backend comparison and re-tracking recovery metrics.
    - _Requirements: 8.4, 8.5_
  - [ ] 7.3 Implement baselines, tolerances, `gate`, and `baseline accept`. Wire the smoke gate into CI and the Kiro hook.
    - _Requirements: 9.1, 9.2, 9.3_

- [ ] 8. Proving Ground
  - [ ] 8.1 Add benchmark tables and migration, typed queries, the authenticated ingest endpoint, and the `benchmark.ingest` job. Integration tests.
    - _Requirements: 10.1_
  - [ ] 8.2 Build the public Proving Ground page and clip comparison view (UI in workbench task 12). Playwright test signed out.
    - _Requirements: 10.2, 10.3, 10.4_
