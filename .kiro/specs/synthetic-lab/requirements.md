# Requirements: Synthetic lab

## Introduction

The synthetic lab generates mechanisms with known ground truth, renders them as realistic and deliberately degraded video, breaks them by removing parts, and measures how well the engine recovers each one. It is the test data source, the property-test generator, the accuracy regression gate, and the source of the public "Proving Ground" page that shows judges and users measured accuracy by mechanism family and difficulty.

## Glossary

- **Family**: a parameterized mechanism template (for example crank-rocker four-bar).
- **Specimen sample**: one generated mechanism with sampled parameters.
- **Breakage**: removal of one or more parts from a sample, with the removed parts as ground truth.
- **Capture profile**: a set of camera, lighting, and degradation settings.
- **Suite**: a versioned, seeded list of samples, breakages, and capture profiles.
- **Proving Ground**: the public page presenting benchmark results.

## Requirements

### Requirement 1: Procedural mechanism generation

**User Story:** As a developer, I want many valid mechanisms across real-world families, so that the engine is tested on the mechanisms old machines use.

#### Acceptance Criteria

1. THE lab SHALL generate samples from these families: four-bar (crank-rocker, double-crank, double-rocker, change-point), slider-crank, inverted slider-crank, Scotch yoke, Watt I and II six-bars, Stephenson I, II, and III six-bars, Chebyshev lambda, Peaucellier–Lipkin, pantograph, Jansen leg, Geneva drive, spur gear train, rack and pinion, belt drive, cam-follower (knife, roller, flat), quick-return (Whitworth), sewing-machine needle bar and take-up lever, flapping-wing automaton, and spatial RSSR.
2. EACH family SHALL define parameter ranges and SHALL reject samples that fail to assemble over the intended driver range.
3. THE lab SHALL generate body outlines, thickness, holes at joints, and decorative non-functional features so that bodies look like real parts.
4. THE lab SHALL compose families into compound machines by attaching one family's output to another's input.
5. THE generated mechanisms SHALL be valid against the shared mechanism schema.

### Requirement 2: Breakage

**User Story:** As a developer, I want broken variants with known missing parts, so that resurrection accuracy can be measured.

#### Acceptance Criteria

1. THE lab SHALL produce breakages that remove one binary link, one slider block, one gear, one belt, or two adjacent links.
2. EACH breakage SHALL record the removed parts and their joints as ground truth and SHALL simulate the broken mechanism's resulting motion, including parts that hang under gravity or move freely when pushed.
3. THE lab SHALL leave the empty holes and wear marks where the removed part attached.

### Requirement 3: 2D renderer

**User Story:** As a developer, I want fast, varied renders, so that the engine is not overfit to one look.

#### Acceptance Criteria

1. THE lab SHALL render planar samples with `skia-python` at configurable resolution and frame rate.
2. THE renderer SHALL randomize materials (cardboard, plywood, brass, steel, painted tin, aged iron), lighting direction, shadows, background textures, and clutter objects.
3. THE renderer SHALL apply a camera model with intrinsics, perspective tilt up to 25 degrees from the plane normal, and lens distortion.
4. THE renderer SHALL render hands or tools occluding parts during configurable intervals.

### Requirement 4: Capture degradations

**User Story:** As a developer, I want footage as bad as real phone video and archival film, so that robustness is measured, not assumed.

#### Acceptance Criteria

1. THE lab SHALL apply handheld camera shake as a band-limited random walk of camera pose.
2. THE lab SHALL apply motion blur by temporal supersampling, rolling shutter, sensor noise, auto-exposure drift, and focus breathing.
3. THE lab SHALL encode with H.264, H.265, and VP9 at randomized quality, with optional variable frame rate and dropped frames.
4. THE lab SHALL apply an archival profile: 12 to 24 fps, film grain, gate weave, flicker, scratches, dust, vignetting, and sepia or monochrome tone.
5. THE lab SHALL record the degradation parameters used for each clip.

### Requirement 5: 3D renderer

**User Story:** As a developer, I want photoreal, multi-view renders of spatial and multi-plane machines, so that spatial reconstruction can be measured.

#### Acceptance Criteria

1. THE lab SHALL render samples in Blender (`bpy`) with Cycles on CPU by extruding outlines to their thickness, with physically based materials and area lighting. 3D clips SHALL be generated on developer machines or CI runners and cached by manifest hash, never rendered on the production VPS.
2. THE lab SHALL render multi-plane and spatial samples from several camera paths, including orbit and handheld paths.
3. THE lab SHALL render per-frame depth and instance masks as ground truth.

### Requirement 6: Ground truth export

**User Story:** As the evaluation harness, I want complete ground truth per clip, so that every pipeline stage can be scored.

#### Acceptance Criteria

1. FOR each clip, THE lab SHALL export the mechanism graph, per-frame body poses, per-frame image projections of every named point with visibility, per-frame instance masks, camera intrinsics and extrinsics per frame, driver values per frame, and the breakage record when present.
2. THE export SHALL use a documented, versioned format: an MP4 clip, a `truth.json` manifest, and Apache Arrow files for per-frame arrays.
3. THE lab SHALL produce short clips for the end-to-end test fixtures.

### Requirement 7: Reproducible suites

**User Story:** As a developer, I want suites that regenerate identically, so that benchmark changes come from code changes only.

#### Acceptance Criteria

1. THE lab SHALL define suites in versioned manifests with seeds, families, breakages, and capture profiles.
2. WHEN a suite is regenerated from the same manifest and lab version, THE lab SHALL produce byte-identical ground truth and content-hash-identical clips.
3. THE lab SHALL provide `smoke` (under 3 minutes on CPU), `core` (under 45 minutes on a GitHub-hosted 4-core runner), and `full` suites.
4. THE lab SHALL store generated suites in object storage keyed by manifest hash and SHALL reuse them when present.

### Requirement 8: Evaluation harness

**User Story:** As a developer, I want each pipeline stage scored against ground truth, so that I know which stage causes a failure.

#### Acceptance Criteria

1. THE harness SHALL run the real engine on each clip through the engine's job API.
2. THE harness SHALL compute: tracking error in pixels and occlusion accuracy; camera motion error; body grouping adjusted Rand index; joint detection precision, recall, and type accuracy; mobility accuracy; link-length relative error; pose RMSE; calibration of reported uncertainty; diagnosis accuracy; resurrection top-1 and top-3 recovery and tie-set correctness; runtime per stage.
3. THE harness SHALL break down every metric by family, capture profile, and difficulty tier.
4. THE harness SHALL run the engine under the reference VPS resource profile (4 CPUs, 8 GB) and SHALL report runtime and peak memory per stage, alongside accuracy.
5. THE harness SHALL compare tracker backends on identical clips and report accuracy, occlusion recovery after model-guided re-tracking, and runtime for each.
6. THE harness SHALL save a run report with the engine version, lab version, suite hash, and per-clip results.

### Requirement 9: Regression gate

**User Story:** As a developer, I want CI to fail when accuracy drops, so that improvements in one area cannot silently break another.

#### Acceptance Criteria

1. THE repository SHALL store accepted baseline metrics per suite with a tolerance per metric.
2. WHEN a run's metric is worse than baseline beyond its tolerance, THE gate SHALL fail and report the metric, family, and clips responsible.
3. WHEN a change improves metrics, THE developer SHALL be able to update the baseline with one command that records the reason.

### Requirement 10: Proving Ground

**User Story:** As a judge or prospective user, I want to see measured accuracy, so that I can trust the reconstructions.

#### Acceptance Criteria

1. WHEN a benchmark run completes on the main branch, THE system SHALL ingest the report into the database.
2. THE web app SHALL present a public Proving Ground page showing the latest results by family, capture profile, and difficulty, with trends across runs.
3. THE Proving Ground SHALL let a visitor open any benchmark clip and see the ground truth, the engine's reconstruction, and the resurrection result side by side.
4. THE Proving Ground SHALL state the failure cases honestly, listing the families and profiles below target accuracy.
