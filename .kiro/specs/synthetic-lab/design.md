# Design: Synthetic lab

## Overview

`tools/lab` is a Python package with a CLI (`orrery-lab`) built on Typer. It uses `orrery_kinematics` for ground-truth motion so lab motion and engine motion come from the same solver.

```
families/ ──► sample ──► (breakage) ──► simulate (orrery_kinematics)
                                            │
                    capture profile ──► render (skia 2D | bpy 3D) ──► degrade ──► encode (FFmpeg)
                                            │
                                    truth.json + Arrow + MP4 ──► object storage (by manifest hash)
                                            │
                     evaluate: engine job API ──► metrics ──► report ──► gate | ingest (Proving Ground)
```

## Families (`lab/families/`)

Each family is a class:

```python
class Family(Protocol):
    name: str
    def parameter_space(self) -> ParameterSpace: ...        # bounded distributions
    def build(self, p: Params, rng: Generator) -> Mechanism: ...
    def driver_range(self, m: Mechanism) -> tuple[float, float]: ...
    def breakable_parts(self, m: Mechanism) -> list[PartRef]: ...
```

- Feasibility: simulate with `orrery_kinematics` and reject samples with `RangeIncomplete`, minimum transmission angle below 20 degrees (configurable per family), or self-collision.
- Appearance: outlines from offset curves around joint anchors (capsule links, gear profiles from involute geometry, cam profiles from Fourier coefficients), holes at joints, randomized decorative cut-outs, rivets, and printed patterns.
- Compound machines: a composer attaches the output body of one family to the driver joint of another through a coupling link or a gear pair.

## Breakage (`lab/breakage.py`)

- A breakage may only select a family's declared `PartRef`. It removes selected bodies or belt joints, every joint incident to a removed body, and any driver left dangling. The versioned ground-truth record retains full removed body, appearance, and joint documents. Surviving attachment sites receive schema points with `role: "hole"`; dressed appearance receives matching holes plus scuff, ring, mesh, or belt wear. Revolute-style anchors must coincide exactly. Prismatic guide references are not falsely treated as coincident anchors.
- Planar dynamics holds surviving drivers at their break-pose value and asks `orrery_kinematics` mobility for the bodies participating in newly free modes. Uniform-density plate mass and inertia come from dressed outlines after subtracting cut-outs and unique holes. The fixed-step velocity-Verlet/RATTLE solver enforces active revolute, prismatic, gear/rack, and belt constraints, prismatic limits, gravity, viscous joint friction, deterministic point impulses, and horizontal-ground restitution and Coulomb friction. Dynamic poses remain frame data; they never mutate the schema graph.
- Total energy is translational plus rotational kinetic energy and gravitational potential relative to the ground line. With friction disabled and no contact, one-second drift must remain below 1%. Spatial and multi-plane free modes, or an active constraint outside the supported planar set, raise an explicit error rather than being silently frozen. Body-to-body impact is deferred to rendering/scene composition; task 2.2's contact surface is the ground plane.

## Renderers

### 2D (`lab/render2d/`)

- A fitted pinhole camera projects the mechanism plane through sampled roll and at most 25° x/y tilt, followed by Brown–Conrady radial and tangential lens distortion. The same immutable camera projects render geometry and named ground-truth points.
- Skia draws one deterministic RGBA canvas per frame. Materials cover cardboard, plywood, brass, steel, painted tin, and aged iron. Surface detail is procedural except for the bundled Poly Haven `wood_planks_grey` 1K diffuse texture (CC0, checksum and attribution in `THIRD_PARTY_MODELS.md`), which is packaged with the lab.
- The renderer draws the frame plate and bosses, moving bodies by layer offset, cut-outs, holes, rivets, breakage wear, material grain, edges, and blurred shadows. Procedural background grain, vignette, and workshop clutter are seeded scene elements and never enter point or mechanism ground truth. Output includes RGBA pixels, PNG bytes, camera parameters, material assignments, and every named point in image pixels.
- Occluders are deterministic vector hand and workshop-tool silhouettes, drawn above parts during validated time intervals. Their image-space motion follows cubic Bézier paths with configurable scale and angle. They never perturb mechanism or point projection ground truth; the renderer separately marks each named point visible or covered from the same silhouette hit test.

### 3D (`lab/render3d/`)

- Blender 5.3 runs as the pinned `bpy` Python module with Cycles forced to one deterministic CPU device and fixed seed/thread settings. It is a developer/CI-only dependency and never runs on the production VPS.
- Planar dressed polygons are embedded through each graph plane's origin, x axis, and normal, then extruded to their thickness and beveled. Spatial bodies are cylinders between their world-coordinate named points using the dressed rod radius. PBR materials, area lights, ground geometry, and stable positive per-body object indices are rebuilt for each scene.
- Seeded orbit paths cover the scene extent. Handheld paths add smooth finite Fourier perturbations instead of frame-wise white-noise jitter. Both paths report full camera extrinsics and clipping bounds.
- Blender Render Layers writes the actual Combined, Z, and IndexOB outputs as lossless 32-bit uncompressed EXR. The lab decodes them into float32 RGB and depth plus int32 instance IDs; background depth is infinity and background instance ID is zero. Rendered clips are later cached by manifest hash so each expensive scene is rendered once.

## Degradations (`lab/degrade/`)

| Degradation | Method |
|---|---|
| Shake | Seeded Fourier camera center, tilt, and roll terms restricted to 0.5–8 Hz; tilt remains within 25° |
| Focus breathing | Low-frequency focal-length trajectory sampled on frame timestamps |
| Motion blur | Box-shutter integration of genuinely rendered temporal supersamples |
| Rolling shutter | Per-row exposure-center offsets with temporal interpolation before shutter integration |
| Noise, exposure | Low-frequency auto-exposure in linear light, then Poisson shot and Gaussian read noise |
| Compression | Real FFmpeg libx264/libx265/libvpx-vp9 with seeded CRF, GOP, pixel format, fixed threads, and deterministic mux metadata |
| VFR, drops | Millisecond presentation timeline with seeded interval jitter; dropped source indices retain explicit timestamp gaps verified by ffprobe |
| Archival | Seeded 12–24 fps resampling, smooth gate weave/flicker, luminance-aware grain, persistent recorded scratches/dust, radial vignette, and linear-light sepia or monochrome tone |

## Ground truth format

```
<suite-hash>/<clip-id>/
  clip.mp4
  truth.json        # lab version, family, params, seed, capture profile, mechanism graph, breakage, intrinsics
  frames.arrow      # per frame: t, driver values, body poses
  points.arrow      # per frame and point: image xy, visible, occluded_by
  masks/            # per frame instance PNGs (16-bit IDs)
  depth/            # 3D renders only, EXR
```

## Suites

- Manifests in `tools/lab/suites/*.toml`. The manifest hash is the SHA-256 of the canonicalized manifest plus the lab version.
- Determinism: one NumPy `Generator` per clip derived from the suite seed and clip index. Encoders run with fixed thread counts and deterministic flags. Clip content hash is computed over decoded frames to remain stable across container metadata.
- Difficulty tiers: `clean`, `phone`, `hostile` (heavy shake, occlusion, low light), `archival`.

## Evaluation (`lab/eval/`)

- Submits each clip through the engine job API (same contract as production), with ground-truth-free inputs.
- Stage metrics computed from engine artifacts:
  - Tracking: median and 90th percentile endpoint error, occlusion accuracy (TAP-Vid style).
  - Body grouping: adjusted Rand index between predicted bodies and true body IDs over tracked points.
  - Joints: match predicted to true joints by body pair and location within tolerance (Hungarian assignment). Report precision, recall, F1, type accuracy.
  - Geometry: relative link-length error after scale alignment, pose RMSE.
  - Uncertainty calibration: fraction of true parameters inside reported 1σ and 2σ intervals (target 68% and 95%).
  - Resurrection: true repair in top-1 and top-3, tie-set contains truth, cognates correctly grouped.
- Reports are JSON with a schema in `packages/engine-contract` so the web app can ingest them.

## Regression gate

- Baselines in `tools/lab/baselines/<suite>.json`. Tolerances are per metric (for example ±0.5 px tracking, −1.0 point F1).
- `orrery-lab gate --suite smoke` exits non-zero on regressions and prints the worst offending clips.
- `orrery-lab baseline accept --suite core --reason "..."` writes the new baseline with the reason in a log.

## Proving Ground persistence

Tables (`packages/db`):

| Table | Columns |
|---|---|
| `benchmark_suite` | id, name, manifest_hash, lab_version, clip_count, created_at |
| `benchmark_run` | id, suite_id, engine_version, git_sha, started_at, finished_at, status, summary jsonb |
| `benchmark_clip` | id, suite_id, family, profile, tier, object_prefix, truth_summary jsonb |
| `benchmark_result` | id, run_id, clip_id, metrics jsonb, artifacts jsonb, failure_reason |

- CI uploads the report to object storage and calls an authenticated ingest endpoint, which enqueues `benchmark.ingest`.
- Public server functions: `listBenchmarkRuns`, `getBenchmarkSummary(runId, groupBy)`, `getBenchmarkClip(clipId, runId)`.

## Correctness properties

1. *For any* family and seed, every accepted sample validates against the schema and assembles over its driver range. **Validates: 1.2, 1.5**
2. *For any* manifest, generating twice yields identical truth files and identical decoded-frame hashes. **Validates: 7.2**
3. *For any* clip, every visible point's projected position lies inside its body's instance mask in that frame (excluding pixels at mask boundaries). **Validates: 6.1**
4. *For any* breakage, the removed parts' anchors coincide with hole points on the remaining bodies. **Validates: 2.1, 2.3**
5. *For any* frictionless broken mechanism, the loose-part dynamics conserve energy within 1% over one second. **Validates: 2.2**

## Testing strategy

- Hypothesis drives family sampling for properties 1, 3, and 4.
- Determinism test (property 2) runs on the smoke manifest in CI.
- Proving Ground: integration tests for ingest and queries, and a Playwright test that opens the page signed out, filters by family, and opens a clip comparison.
