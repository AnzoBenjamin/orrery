# Design: Vision pipeline

## Overview

```
                    browser (visitor's GPU): SAM 2.1 part outlining ──► mask annotations ─┐
                                                                                           ▼
footage ─► ingest ─► window ─► camera motion ─► seeding ─► tracking (KLT) ─► grouping ─► joints ─► mobility/driver ─► fit
                                                              ▲                                                       │
                                                              └──── model-guided re-tracking (≤ 3 rounds) ◄───────────┘
                                                                                                                      ▼
                                                                      body regions ─► (diagnosis) ─► overlay
```

The engine (`services/engine`) is a FastAPI app running on CPU only. Each analysis is a job with a stage graph. Stages are pure functions from input artifacts to output artifacts plus events. A stage runner handles artifact persistence through the job's upload grants, checkpointing, cancellation, and progress events.

### Why this works without a GPU

- Mechanisms are rigid bodies with few degrees of freedom. Once a first model is fitted, every point's position in every frame is predicted. Tracking becomes a local search around a prediction, which classical methods do well and cheaply.
- Segmentation is only needed for corrections and outlines. Grouping uses motion, outlines come from tracks plus GrabCut on a few keyframes, and outlines propagate by rigid motion. Interactive segmentation runs in the user's browser.
- The heavy numerical work (fitting, simulation, resurrection search) is the Rust solver, which is CPU work in any case.

## Persistence (web app side)

| Table | Columns |
|---|---|
| `analysis` | id, specimen_id, kind (`reconstruct`, `diagnose`, `verify`), footage_ids uuid[], window jsonb (per footage start_ms, end_ms, source `user` or `auto`), status (`queued`, `running`, `awaiting_input`, `succeeded`, `failed`, `canceled`), queue_position, current_stage, progress, eta_seconds, engine_version, params jsonb, error jsonb, trace_id, created_at, started_at, finished_at |
| `analysis_stage` | id, analysis_id, stage, status, started_at, finished_at, runtime_ms, peak_rss_bytes, metrics jsonb, input_hash |
| `analysis_event` | analysis_id, seq, type, payload jsonb, received_at. Unique (analysis_id, seq) |
| `analysis_input_request` | id, analysis_id, stage, kind, payload jsonb, preferred_option, confidence, status (`open`, `answered`, `expired`), response jsonb, answered_by, answered_at |
| `annotation` | id, footage_id, frame_index, kind (`part_mask`, `part_prompt`, `joint`, `ground`, `scale_segment`, `exclude_region`, `marker_color`), geometry jsonb, value jsonb, source (`sam_browser`, `manual`), created_by, created_at |
| `artifact` | id, analysis_id, stage, slot, object_key, format, byte_size, sha256, meta jsonb |
| `analysis_allowance` | user_id, day, used, limit |
| `diagnosis_finding` | id, analysis_id, kind (`loose_body`, `frozen_body`, `empty_hole`, `missing_joint`, `missing_body`), refs jsonb, evidence jsonb, confidence |
| `mechanism` / `mechanism_revision` | defined in the workbench design. A successful fit creates a mechanism with an `engine` revision |

Server functions: `suggestWindow`, `startAnalysis`, `cancelAnalysis`, `answerInputRequest`, `submitCorrection(stage, annotations)`, `getAnalysis`, `listAnalyses`, `getArtifactUrl`, `getAllowance`. Each creates domain events for SSE.

## Scheduling

- The worker owns one pg-boss queue `engine.analysis` with `teamConcurrency` equal to `ENGINE_CONCURRENCY` (default 1). Queue position and ETA come from the queue order and the median runtime of recent analyses, adjusted by clip length.
- An analysis waiting on input is checkpointed and its job completes with state `awaiting_input`. Answering enqueues a resume job, so waiting never holds a slot.
- The engine container runs with a CPU quota of `nproc − 1` and a memory limit. Inside, OpenCV and the solver use that many threads. Resurrection searches use a process pool of the same size.

## Engine stages

### Ingest

- PyAV decode, rotation, color conversion to BT.709 RGB, constant timeline at the median frame interval with original PTS recorded.
- PySceneDetect content detector for shot cuts. Multi-shot footage raises `choose_shots`.
- Analysis copy: frames resized to the configured long side (default 960 px), stored as a lossless frame cache on local disk for the job's lifetime. Full-resolution frames are decoded on demand by index.
- Proxy video: H.264 at 720p with keyframes every 6 frames for browser scrubbing. Thumbnails as WebP.

### Window

- Pre-pass at 320 px and every second frame: stabilized frame difference energy per frame, plus a global motion signal from Farneback flow.
- Period from the autocorrelation peak of the motion signal. The window covers 2 to 4 periods, minimizing a cost of camera motion plus occlusion proxy (sudden energy spikes). User-chosen windows skip this stage.

### Camera motion

- Static mask: low Farneback flow magnitude across a sliding window on the analysis copy.
- Per-frame homography to a reference frame from ORB features in the static mask with OpenCV USAC MAGSAC++.
- Parallax test: residuals of static features after homography. Above threshold, set `requires_spatial`. Until `spatial-reconstruction` lands, the engine asks for a steadier or more frontal clip and records the routing reason.
- After grouping, recompute homographies using ground-body tracks only.

### Seeding

- Moving-region mask: stabilized frame differencing and flow magnitude, closed and dilated.
- Shi-Tomasi corners in the moving mask on a grid of cells, with a per-cell cap, so coverage is even. Up to 3,000 seeds.
- Holes: on 5 keyframes at full resolution, Hough circles cross-checked by contour circularity and consistent appearance across keyframes.
- Markers: `cv2.aruco` (dictionary `DICT_4X4_100`, matching the printable marker sheet) with sub-pixel corners. Colored dots: HSV thresholding on a user-chosen color (`marker_color` annotation) with blob centroid refinement.
- User points from `joint` and `part_prompt` annotations.

### Tracking

- Adapter interface:

```python
class PointTracker(Protocol):
    name: str
    def track(self, frames: FrameSource, seeds: Seeds, predictor: PosePredictor | None) -> Tracks: ...
```

- Default backend `klt`: OpenCV `calcOpticalFlowPyrLK` on grayscale analysis frames, 21×21 window, 4 pyramid levels.
  - Forward-backward check: track back one frame and reject when the round-trip error exceeds 0.5 px.
  - Appearance check: normalized cross-correlation of the current patch against the point's reference patch. Reject below 0.8.
  - Rejected points become occluded, not deleted, so re-tracking can recover them.
  - Re-seeding every 15 frames in cells whose live track count drops below half the original.
- Markers bypass KLT: they are detected per frame and are always high confidence.
- Optional backend `cotracker3_onnx`: CoTracker3 exported to ONNX and run with ONNX Runtime on CPU at 384 px in windows of 16 frames. It stays off unless synthetic-lab task 7 shows a gain on the `phone` and `hostile` tiers and the stage stays within budget. CoTracker3 weights are CC-BY-NC 4.0, noted in `THIRD_PARTY_MODELS.md`.

### Body grouping

- Affinity between tracks i and j: `exp(−Var_t(d_ij(t)) / σ²)` over frames where both are visible, with σ from the tracking noise estimate. Shared membership in a `part_mask` annotation multiplies affinity. Membership in different masks sets it near zero.
- Spectral clustering with the cluster count from the eigengap, then per-cluster RANSAC rigid fit (SE(2) in the stabilized frame). Clusters with high residuals split recursively. Non-rigid clusters become compliant candidates.
- Ground: largest cluster with near-zero motion in the stabilized frame. Close calls raise `confirm_ground`.

### Joint discovery

For each body pair (A, B), compute the relative motion of B in A's frame over time, then fit:

| Hypothesis | Test |
|---|---|
| revolute | least-squares fixed point in both frames (instantaneous centers consistent over time) |
| prismatic | relative rotation constant and relative translation along a line |
| pin-in-slot | a point of B traces a fixed curve in A while B rotates relative to A |
| gear mesh | constant angular velocity ratio, both bodies revolute to a common carrier, center distance matches pitch radii |
| belt | constant ratio, no contact required |
| cam follower | follower coordinate is a smooth periodic function of cam angle with contact at the predicted profile |

- Score each by BIC using the residual variance and parameter count. "None" is always a hypothesis.
- Hole snapping: when a revolute center lies within 2σ of a detected hole, refit with the hole as a prior.
- Graph assembly: choose the joint set maximizing total evidence subject to connectivity to ground and agreement between model mobility (mechanism-core) and the observed motion dimension. Search with greedy addition and local swaps.

### Mobility, driver, phase

- Observed dimension: local PCA on the stacked body pose trajectories, counting significant components.
- Driver: candidates are full-rotation revolute joints to ground, chosen by smoothness of the unwrapped angle, or by `choose_driver`.
- Aliasing: when the frame-to-frame rotation exceeds π/2 or the angle appears to reverse periodically, evaluate rate hypotheses `ω + k·2π·fps` for small k and choose by fit residual plus a smoothness prior.

### Fit

- Calls `orrery_kinematics.fit` with the topology, initial geometry from joint discovery, observations in the stabilized frame, and per-frame planar homographies.
- Two passes: Huber loss, then 3σ outlier rejection and refit.
- Non-convergence produces `choose_joint_hypothesis`, `place_joint`, or `outline_part` requests on the worst bodies.

### Model-guided re-tracking

For each round (at most 3):

1. Predict every occluded or rejected point's image position per frame from fitted body poses, the camera homography, and the point's body-local coordinates.
2. Warp the point's reference patch by the predicted relative body motion (rotation and scale from the homography).
3. Search a window of radius `max(8 px, 3σ_pred)` with normalized cross-correlation, then refine sub-pixel with one LK step from the best match.
4. Accept when the NCC score exceeds 0.85 and the offset from the prediction is within 3σ_pred.
5. Refit. Stop when the cost improves by less than 1% or round 3 completes.

Per-body observed fraction before and after re-tracking is stored in stage metrics and shown in the analysis view.

### Body regions

- Keyframe region per body: the user's `part_mask` when present. Otherwise the concave hull (alpha shape) of the body's tracks, used to initialize OpenCV GrabCut on the full-resolution keyframe.
- Regions from several keyframes are mapped into the body frame and fused by voting into one body outline polygon, which is simplified and stored as `outline.polygonLocal` in the graph.
- Per-frame regions are the outline transformed by the fitted pose. No per-frame segmentation runs.

### Browser part outlining (web app, documented here for the contract)

- SAM 2.1 tiny or small (Apache-2.0) in ONNX format, loaded with transformers.js in a dedicated Web Worker. WebGPU backend when `navigator.gpu` is available, otherwise WebAssembly with SIMD and threads.
- The image encoder runs once per selected frame. Each tap or box re-runs only the prompt decoder, which is fast enough for interactive use.
- Before first use, the worker runs a timed probe. If one encoder pass would exceed 8 seconds, the UI offers the polygon and brush tools instead.
- Output masks are simplified to polygons and saved as `part_mask` annotations with `source: "sam_browser"`. Model weights are served from our own Garage bucket with long cache lifetimes, not from a third-party CDN.

### Scale

- Priority: user measurement annotation, detected reference object (ArUco tag from the marker sheet at its printed size, ID-1 card, configured coins), device intrinsics with depth from the ground plane fit.
- Lens distortion from straight edges with a one-parameter division model when intrinsics are absent.

### Diagnosis

- Fit the broken footage the same way.
- Loose bodies: observed motion dimension exceeds mobility of the fitted constrained subsystem, or a body's motion is gravity-dominated (it falls between frames when not pushed).
- Frozen bodies: zero motion while connected parts move.
- Empty holes: detected holes with no joint after fitting.
- With a reference model: match bodies by appearance (DINOv2 ViT-S/14 embeddings of body-region crops, run with ONNX Runtime on CPU) and by geometry, then report reference joints and bodies with no match.

### Overlay

- Per frame: body poses as image-space affine transforms, body outlines, joint image positions, track positions and visibility, per-body residuals. Stored as Arrow, chunked by 120 frames, so the browser can stream chunks.

## API

- `POST /v1/jobs` (contract from platform-foundation), `POST /v1/jobs/{id}/cancel`, `POST /v1/jobs/{id}/inputs` (answers and corrections), `POST /v1/probe`, `POST /v1/window` (window suggestion for the trim control).

## Error handling

- Stage errors are typed (`UnsupportedFootage`, `NoMotionDetected`, `TooFewTracks`, `GroundAmbiguous`, `FitDiverged`, `RequiresSpatial`, `WindowTooLong`, `AllowanceExceeded`) and map to a designed message plus a suggested action in the UI. `TooFewTracks` suggests printing the marker sheet.

## Correctness properties

1. *For any* synthetic clip with camera shake, stabilized ground-body points stay within 1 px RMS of their mean position. **Validates: 5.1, 5.2**
2. *For any* synthetic clip, body grouping ARI is at least 0.9 on the `clean` tier and 0.8 on `phone`. **Validates: 9.1, 9.2**
3. *For any* synthetic clip, joint detection F1 is at least 0.9 on `clean` and type accuracy at least 0.95 for detected joints. **Validates: 12.1, 12.2**
4. *For any* re-run of a stage with identical inputs, outputs are identical. **Validates: 3.2, 3.5**
5. *For any* clip whose rotation rate aliases at the given frame rate, the selected rate hypothesis matches ground truth. **Validates: 13.4**
6. *For any* fitted synthetic clip, true parameters fall inside the reported 2σ interval at least 90% of the time. **Validates: 14.2**
7. *For any* broken synthetic clip, the removed part's anchor holes appear in diagnosis findings. **Validates: 17.2**
8. *For any* synthetic clip with occlusion intervals, model-guided re-tracking recovers at least 85% of occluded point-frames within 1.5 px of truth, and never lowers the fit's pose accuracy. **Validates: 8.1–8.4**
9. *For any* synthetic clip, the fused body outline has IoU of at least 0.85 with the true outline after rigid alignment. **Validates: 11.1–11.3**
10. *For any* clip with markers, marker tracks have median error below 0.3 px. **Validates: 7.3**
11. *For any* suite clip on the reference VPS profile, end-to-end runtime stays within the budget in 4.1. **Validates: 4.1**

Targets in properties 2, 3, 6, 8, 9, and 11 are initial values and are tracked by the synthetic-lab gate.

## Testing strategy

- Unit tests per stage on small synthetic inputs with hypothesis.
- Stage metrics, including runtime and peak memory, through the synthetic-lab harness with baselines. CI runs the harness with the engine container limited to the reference VPS profile (4 CPUs, 8 GB).
- End-to-end: Playwright uploads a fixture clip, accepts the suggested window, watches stages and queue position over SSE, answers a `confirm_ground` request, outlines a part with the in-browser model (WebAssembly backend in CI), sees the fitted overlay and the re-tracking gain, and submits a correction that re-runs later stages.
