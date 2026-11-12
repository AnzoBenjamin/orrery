# Requirements: Vision pipeline

## Introduction

The vision pipeline turns footage into a fitted mechanism graph with uncertainty. It runs on CPU only, in the engine service on a single VPS, as staged, resumable jobs. GPU-class work is either replaced by classical computer vision that uses the mechanism model as a constraint, or moved into the user's browser (part outlining on the visitor's own GPU through WebGPU). It works without markers or manual joint clicks, gets faster and more exact when markers are present, and accepts user corrections at any stage. When the evidence is ambiguous, it asks the user a specific question instead of guessing. For broken footage it diagnoses which constraints are missing, which feeds the resurrection spec.

## Glossary

- **Analysis**: one engine run over one or more footage items of a specimen.
- **Analysis window**: the time range of a footage item the engine processes.
- **Stage**: one step of the pipeline with its own artifacts and progress.
- **Track**: a point's image trajectory with per-frame visibility and confidence.
- **Model-guided re-tracking**: using the fitted mechanism to predict where lost points should be, then searching for them there.
- **Body region**: the image area belonging to one body, from a browser-generated mask or from the body's tracks.
- **Input request**: a question the engine asks the user to continue (for example "Which part is fixed to the table?").
- **Overlay**: per-frame rendering data that aligns the fitted model to the video.
- **Reference VPS**: 4 vCPU, 8 GB RAM, no GPU. Performance targets are stated against it.

## Requirements

### Requirement 1: Footage ingestion

**User Story:** As a user, I want any phone or archival video to be accepted and normalized, so that I do not have to convert files.

#### Acceptance Criteria

1. THE engine SHALL decode common containers and codecs (MP4, MOV, MKV, WebM, AVI; H.264, H.265, VP9, AV1, ProRes, MJPEG) with PyAV.
2. THE engine SHALL apply rotation metadata, convert to a standard color space, and resample variable frame rate footage to a constant timeline while recording original timestamps.
3. THE engine SHALL detect shot cuts and, WHEN footage contains several shots, SHALL ask the user which shots to analyze.
4. THE engine SHALL read device intrinsics from metadata when present.
5. THE engine SHALL produce an analysis copy downscaled to a configurable long side (default 960 px) and SHALL keep access to full-resolution frames for hole detection, marker detection, and scale measurement.

### Requirement 2: Analysis window

**User Story:** As a user with a long clip, I want the engine to analyze only the useful part, so that results arrive quickly.

#### Acceptance Criteria

1. THE user SHALL be able to choose the analysis window on a trim control before starting an analysis.
2. WHEN the user does not choose a window, THE engine SHALL run a fast motion pre-pass, detect the cycle period, and select a window covering two to four full cycles with the least camera motion and occlusion.
3. THE analysis window SHALL NOT exceed 90 seconds. WHEN the selected range is longer, THE system SHALL explain the limit and propose the best 90-second window.

### Requirement 3: Analysis lifecycle

**User Story:** As a user, I want analysis to be reliable and visible, so that I can leave and return without losing work.

#### Acceptance Criteria

1. THE system SHALL run analyses through the stages: ingest, camera motion, seeding, tracking, body grouping, joint discovery, mobility and driver, fit, model-guided re-tracking and refit, body regions, diagnosis (for broken footage), overlay.
2. THE engine SHALL persist each stage's artifacts and SHALL resume a retried analysis from the last completed stage.
3. THE engine SHALL report progress per stage with a fraction, a human-readable description, and an estimated time remaining.
4. WHEN a user cancels an analysis, THE engine SHALL stop within 10 seconds and release its worker slot.
5. WHEN a user corrects the output of a stage, THE system SHALL re-run only that stage and later stages.
6. WHILE analyses wait for a free worker slot, THE system SHALL show each waiting user their queue position and estimated start time.

### Requirement 4: Compute budget

**User Story:** As the operator of one CPU-only VPS, I want analysis to stay within the server's capacity, so that the site stays responsive while the engine works.

#### Acceptance Criteria

1. ON the reference VPS, THE engine SHALL complete a 30-second 1080p clip of a planar mechanism with up to 10 bodies end to end in under 4 minutes.
2. THE engine SHALL run analyses with a configurable concurrency (default 1) and SHALL be limited by container CPU and memory quotas so that the web app keeps at least one core.
3. THE engine SHALL record per-stage runtime and peak memory in stage metrics.
4. THE system SHALL limit analyses per user per day (configurable) and SHALL show the remaining allowance.

### Requirement 5: Camera motion

**User Story:** As a user filming by hand, I want camera shake removed, so that I do not need a tripod.

#### Acceptance Criteria

1. THE engine SHALL estimate per-frame camera motion from static scene regions using robust homography estimation (MAGSAC++).
2. THE engine SHALL refine the static reference to the ground body once body grouping completes, and SHALL express all fitted motion relative to the ground body.
3. WHEN residual parallax indicates the scene is not well approximated by a plane, THE engine SHALL route the analysis to spatial reconstruction and inform the user.
4. THE engine SHALL report the stabilization quality and SHALL produce a stabilized preview artifact.

### Requirement 6: Track seeding

**User Story:** As the engine, I want track points placed where motion and texture make them reliable, so that tracking succeeds without a learned model.

#### Acceptance Criteria

1. THE engine SHALL seed tracks at strong corner features inside moving regions, found by stabilized frame differencing and dense optical flow on the analysis copy.
2. THE engine SHALL seed tracks at detected circular holes and pivots, at detected markers, and at points the user placed.
3. THE engine SHALL keep seed density even across moving regions so that every visibly moving part receives tracks.
4. THE engine SHALL re-seed during tracking in moving regions whose track coverage drops below a threshold.

### Requirement 7: Point tracking

**User Story:** As the engine, I want accurate long-range point tracks through blur and occlusion on a CPU, so that motion can be fitted without markers or a GPU.

#### Acceptance Criteria

1. THE engine SHALL track points with pyramidal Lucas–Kanade optical flow, rejecting points that fail a forward-backward consistency check or a patch appearance check.
2. THE engine SHALL output visibility and confidence per point per frame and SHALL NOT report positions for occluded or rejected frames as observed.
3. WHEN markers are present (ArUco tags or colored dots of a user-chosen color), THE engine SHALL detect them on full-resolution frames with sub-pixel corner refinement and use them as high-confidence tracks.
4. THE engine SHALL use a tracker adapter so that additional backends can be added. A learned backend running on CPU through ONNX Runtime (CoTracker3) SHALL be enabled only if the synthetic-lab benchmark shows it improves accuracy and fits the compute budget.

### Requirement 8: Model-guided re-tracking

**User Story:** As a user with blurry footage or a hand in the way, I want the engine to recover lost points using what it knows about the mechanism, so that occlusions do not break the reconstruction.

#### Acceptance Criteria

1. AFTER the first fit, THE engine SHALL predict every lost or rejected point's position in every frame from the fitted body poses.
2. THE engine SHALL search for each lost point in a window around its prediction, by normalized cross-correlation against the point's reference patch warped by the predicted body motion.
3. THE engine SHALL accept a recovered position only when the match score and its agreement with the prediction both exceed thresholds, and SHALL then refit.
4. THE engine SHALL repeat prediction, re-tracking, and refitting until the fit stops improving or three rounds complete.
5. THE engine SHALL record, per body, the fraction of frames observed before and after re-tracking.

### Requirement 9: Body grouping

**User Story:** As the engine, I want tracks grouped into rigid parts, so that each part becomes a body in the model.

#### Acceptance Criteria

1. THE engine SHALL group tracks into rigid bodies using pairwise rigidity (variance of inter-point distance over time in the stabilized frame), boosted by shared membership in a user-provided part mask when one exists.
2. THE engine SHALL verify each group with a robust rigid-motion fit and SHALL split groups whose residuals exceed the noise level.
3. THE engine SHALL identify the ground body as the largest group that is static relative to the scene, and SHALL ask the user to confirm when two candidates are close.
4. THE engine SHALL flag non-rigid groups as compliant candidates (springs, belts, strings).

### Requirement 10: Part outlining in the browser

**User Story:** As a user, I want to tap a part and have its outline drawn for me, so that I can add, split, or fix parts in seconds.

#### Acceptance Criteria

1. THE web app SHALL run a SAM 2.1 segmentation model in the browser through ONNX Runtime Web, on WebGPU when available and on WebAssembly otherwise, so that no segmentation runs on the server.
2. WHEN the user taps or draws a box on a frame, THE web app SHALL produce a part mask on that frame and let the user refine it with more taps.
3. WHEN neither WebGPU nor a fast enough WebAssembly path is available, THE web app SHALL offer polygon and brush tools instead.
4. THE web app SHALL submit masks to the server as annotations (polygons in image coordinates of the named frame), and THE engine SHALL use them to add, split, merge, or remove bodies.

### Requirement 11: Body regions and outlines

**User Story:** As a user, I want each part's real shape known in every frame, so that the overlay looks right and replacement parts match the originals.

#### Acceptance Criteria

1. THE engine SHALL derive each body's region on keyframes from a user mask when one exists, or otherwise from the concave hull of its tracks refined with GrabCut.
2. THE engine SHALL propagate each body's region to every frame by its fitted rigid motion instead of segmenting each frame.
3. THE engine SHALL store each body's outline in the body's local frame in the mechanism graph.
4. THE engine SHALL detect circular holes and empty pivot holes inside body regions on full-resolution keyframes and record them as candidate anchor points.

### Requirement 12: Joint discovery

**User Story:** As the engine, I want to infer how parts connect and what kind of joint each connection is, so that the model reflects the real mechanism.

#### Acceptance Criteria

1. FOR each pair of bodies, THE engine SHALL evaluate hypotheses: none, revolute, prismatic, pin-in-slot, gear mesh, belt, and cam-follower.
2. THE engine SHALL select among hypotheses by an information criterion (BIC) on the relative motion, and SHALL record the selected joint's confidence.
3. THE engine SHALL prefer joint anchor locations that coincide with detected holes when the fit supports them.
4. THE engine SHALL assemble the joint graph so that it is connected to ground and SHALL reject joint sets whose mobility contradicts the observed motion dimension.

### Requirement 13: Mobility, driver, and phase

**User Story:** As a user, I want the engine to find what drives the machine and the crank position in every frame, so that the simulation can be compared frame by frame.

#### Acceptance Criteria

1. THE engine SHALL estimate the observed number of independent motions from the body pose trajectories by rank analysis.
2. THE engine SHALL propose the driver joint (a full-rotation revolute to ground with the smoothest coordinate, or a user selection).
3. THE engine SHALL estimate driver values per frame, unwrapped over multiple turns.
4. WHEN the frame rate is low relative to rotation speed, THE engine SHALL evaluate several rotation-speed hypotheses (to resolve the wagon-wheel effect) and select by fit residual and smoothness.
5. THE engine SHALL detect cyclic motion and estimate the period.

### Requirement 14: Fit and uncertainty

**User Story:** As a user, I want a model that matches the video and states how sure it is, so that I can trust or correct it.

#### Acceptance Criteria

1. THE engine SHALL fit the mechanism with the mechanism-core fitter using tracks, visibility, and confidence.
2. THE engine SHALL produce a mechanism graph with per-parameter uncertainty and per-body and per-joint confidence.
3. THE engine SHALL report reprojection error per body and flag bodies with residuals above the noise level.
4. WHEN the fit fails to converge, THE engine SHALL report which bodies and joints are inconsistent and request user input.

### Requirement 15: Input requests

**User Story:** As a user, I want the engine to ask me specific questions when it is unsure, so that I can resolve ambiguity in seconds.

#### Acceptance Criteria

1. THE engine SHALL raise input requests of types: choose shots, confirm ground, outline a part, place a joint, choose driver, set scale, and choose between joint hypotheses.
2. EACH input request SHALL include the frame, the image region, the options, and the engine's preferred option with its confidence.
3. WHEN the user answers, THE engine SHALL continue from the stage that raised the request.
4. WHILE an analysis waits for an answer, THE engine SHALL release its worker slot so other analyses can run, and SHALL resume from its checkpoint when answered.

### Requirement 16: Scale and intrinsics

**User Story:** As a restorer, I want real-world dimensions, so that a repair part can be fabricated.

#### Acceptance Criteria

1. THE engine SHALL establish scale from, in order of preference: a user measurement between two points, a detected reference object of known size (ArUco marker from the printed marker sheet, ISO/IEC 7810 ID-1 card, coin from a configured set), or device intrinsics with an estimated distance.
2. THE engine SHALL record the scale source and its uncertainty in the mechanism graph.
3. THE engine SHALL estimate lens distortion from straight edges when intrinsics are unavailable.

### Requirement 17: Broken-footage diagnosis

**User Story:** As a restorer, I want the engine to tell me what is missing, so that I know what to repair.

#### Acceptance Criteria

1. WHEN footage is marked broken, THE engine SHALL compare observed motion against what a complete mechanism of the observed parts could produce.
2. THE engine SHALL identify bodies with excess freedom (loose or hanging parts), bodies that no longer move, and empty holes, and SHALL report them as diagnosis findings.
3. WHEN a reference model exists for the specimen, THE engine SHALL align the broken model to it and report which joints and bodies are absent.
4. THE engine SHALL output a diagnosis artifact consumed by the resurrection spec.

### Requirement 18: Overlay and artifacts

**User Story:** As a user, I want the fitted model drawn on the video, so that I can see where it is right or wrong.

#### Acceptance Criteria

1. THE engine SHALL produce per-frame overlay data: body poses in image coordinates, body outlines, joint positions, track positions with visibility, and residuals.
2. THE engine SHALL produce compact artifacts (Arrow for arrays, WebP for thumbnails, a downscaled proxy video with frequent keyframes for scrubbing).
3. THE web app SHALL load overlay data progressively so scrubbing starts before all artifacts download.
