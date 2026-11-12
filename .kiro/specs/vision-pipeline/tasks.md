# Tasks: Vision pipeline

- [ ] 1. Engine service and stage runner
  - [ ] 1.1 Create the FastAPI app with contract models, service-token auth, job intake, stage graph, artifact upload via grants, checkpoint and resume, cancellation, and signed event callbacks.
    - _Requirements: 3.1, 3.2, 3.3, 3.4_
  - [ ] 1.2 Add analysis tables (including window, queue position, ETA, allowance), migration, typed queries, server functions, and worker dispatch. Integration tests.
    - _Requirements: 3.1–3.4, 4.4_
  - [ ] 1.3 Build the CPU-only engine image without PyTorch (ONNX Runtime for models). Implement the `engine.analysis` queue with configurable concurrency, queue position and ETA events, container CPU and memory limits, per-stage runtime and peak memory metrics, and slot release while awaiting input.
    - _Requirements: 3.6, 4.2, 4.3, 15.4_

- [ ] 2. Ingest and window
  - [ ] 2.1 Implement decode, rotation, color conversion, VFR normalization, intrinsics from metadata, the downscaled analysis copy with full-resolution access, proxy video, and thumbnails.
    - _Requirements: 1.1, 1.2, 1.4, 1.5, 18.2_
  - [ ] 2.2 Implement shot detection and the `choose_shots` input request.
    - _Requirements: 1.3, 15.1_
  - [ ] 2.3 Implement the motion pre-pass, period detection, automatic window selection, the 90-second limit, and `suggestWindow`.
    - _Requirements: 2.1, 2.2, 2.3_

- [ ] 3. Camera motion
  - [ ] 3.1 Implement the Farneback static mask, MAGSAC++ homographies, the parallax test with spatial routing, and the stabilized preview. Property test 1.
    - _Requirements: 5.1, 5.3, 5.4_

- [ ] 4. Seeding and tracking
  - [ ] 4.1 Implement moving-region seeding with even coverage, full-resolution hole detection, user points, and re-seeding.
    - _Requirements: 6.1–6.4, 11.4_
  - [ ] 4.2 Implement the tracker adapter and the `klt` backend with forward-backward and appearance checks.
    - _Requirements: 7.1, 7.2, 7.4_
  - [ ] 4.3 Implement ArUco and colored-dot marker tracks with sub-pixel refinement and the `marker_color` annotation. Property test 10.
    - _Requirements: 7.3_
  - [ ] 4.4 Implement the `cotracker3_onnx` backend, benchmark it against `klt` on the `core` suite under the reference VPS profile, and record the decision and numbers in `tech.md`.
    - _Requirements: 7.4_

- [ ] 5. Body grouping
  - [ ] 5.1 Implement rigidity affinity with mask boosting, spectral clustering with eigengap, RANSAC verification and splitting, compliant flagging, ground selection, and `confirm_ground`. Property test 2.
    - _Requirements: 9.1–9.4_

- [ ] 6. Joint discovery
  - [ ] 6.1 Implement the six joint hypothesis fitters and BIC selection.
    - _Requirements: 12.1, 12.2_
  - [ ] 6.2 Implement hole snapping and graph assembly with mobility agreement. Property test 3.
    - _Requirements: 12.3, 12.4_

- [ ] 7. Mobility, driver, phase
  - [ ] 7.1 Implement observed-dimension estimation, driver selection with `choose_driver`, phase unwrapping, period detection, and aliasing hypotheses. Property test 5.
    - _Requirements: 13.1–13.5_

- [ ] 8. Fit, re-tracking, scale
  - [ ] 8.1 Integrate `orrery_kinematics.fit` with two-pass robust fitting, residual reporting, and non-convergence input requests. Property test 6.
    - _Requirements: 14.1–14.4_
  - [ ] 8.2 Implement model-guided re-tracking (prediction, warped-patch NCC search, acceptance, refit loop) and per-body observed-fraction metrics. Property test 8.
    - _Requirements: 8.1–8.5_
  - [ ] 8.3 Implement scale from user measurement, marker-sheet ArUco tags, ID-1 cards, coins, and intrinsics, plus lens distortion from straight edges. `set_scale` input request.
    - _Requirements: 16.1, 16.2, 16.3_

- [ ] 9. Body regions and browser outlining
  - [ ] 9.1 Implement keyframe regions from masks or concave hull plus GrabCut, outline fusion in the body frame, and propagation by fitted pose. Property test 9.
    - _Requirements: 11.1, 11.2, 11.3_
  - [ ] 9.2 Implement the browser segmentation worker: SAM 2.1 ONNX through transformers.js, WebGPU with WebAssembly fallback, the timed capability probe, weights served from Garage, mask-to-polygon conversion, and `part_mask` annotations. UI in workbench task 6.2.
    - _Requirements: 10.1, 10.2, 10.3, 10.4_
  - [ ] 9.3 Use `part_mask` annotations in grouping and the `outline_part` input request.
    - _Requirements: 9.1, 10.4, 15.1_

- [ ] 10. Input requests
  - [ ] 10.1 Implement the input request table, `answerInputRequest`, checkpointed resume jobs, and expiry.
    - _Requirements: 15.1–15.4_

- [ ] 11. Diagnosis
  - [ ] 11.1 Implement loose, frozen, and empty-hole findings and reference alignment with DINOv2 ViT-S/14 on ONNX Runtime. Add `diagnosis_finding` table and queries. Property test 7.
    - _Requirements: 17.1–17.4_

- [ ] 12. Overlay
  - [ ] 12.1 Implement chunked Arrow overlay output with outlines and progressive loading support in `getArtifactUrl`.
    - _Requirements: 18.1, 18.2, 18.3_

- [ ] 13. Budget and end-to-end
  - [ ] 13.1 Add the runtime budget check (property 11) to the lab gate, run with the engine limited to 4 CPUs and 8 GB.
    - _Requirements: 4.1_
  - [ ] 13.2 Playwright test: upload fixture clip, accept the suggested window, watch stages and queue position over SSE, answer `confirm_ground`, outline a part in the browser, inspect overlay and re-tracking gain, submit a correction and observe partial re-run, cancel a second analysis.
    - _Requirements: 2.1, 3.1–3.6, 10.1–10.4, 15.1–15.3_
