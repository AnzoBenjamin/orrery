# Tasks: Resurrection

- [ ] 1. Persistence and server layer
  - [ ] 1.1 Add resurrection tables and migration, typed queries, and server functions with authorization. Integration tests.
    - _Requirements: 10.1, 10.3_

- [ ] 2. Target motion
  - [ ] 2.1 Implement target motion construction from same-machine reference, other-unit footage (Umeyama alignment and phase cross-correlation), traced paths, and mechanism revisions. Property test 6.
    - _Requirements: 1.1, 1.2, 4.1_
  - [ ] 2.2 Implement output selection and weights, and plausibility-only mode labeling.
    - _Requirements: 1.3, 1.4_

- [ ] 3. Candidate generation
  - [ ] 3.1 Implement anchor-site sampling and binary-link candidates with distance-bound filtering.
    - _Requirements: 2.1, 2.2_
  - [ ] 3.2 Implement slider, gear, and belt candidates.
    - _Requirements: 2.3_
  - [ ] 3.3 Generate the kinematic chain atlas with `pynauty` and implement two-part topology candidates.
    - _Requirements: 2.4_
  - [ ] 3.4 Implement the batch assembly filter.
    - _Requirements: 2.5_

- [ ] 4. Refinement and scoring
  - [ ] 4.1 Implement parallel refinement with existing-geometry priors and hole-snapping likelihood-ratio test.
    - _Requirements: 3.1, 3.2, 3.3_
  - [ ] 4.2 Implement Fréchet and timing errors, plausibility penalties, rewards, and decomposed scoring. Property test 4.
    - _Requirements: 4.1, 4.2, 4.3, 5.1, 5.2, 5.3_
  - [ ] 4.3 Tune weights on the `core` suite and record them with the suite hash. Property test 1 in the lab gate.
    - _Requirements: 4.1, 5.1_

- [ ] 5. Ties, cognates, disambiguation
  - [ ] 5.1 Implement covariance sampling, score distributions, and tie grouping.
    - _Requirements: 6.1, 6.3_
  - [ ] 5.2 Implement cognate detection, including analytic Roberts–Chebyshev cognates. Property test 2.
    - _Requirements: 6.2_
  - [ ] 5.3 Implement disambiguation step selection, `answerDisambiguation`, and the re-rank job. Property test 3.
    - _Requirements: 7.1, 7.2, 7.3_

- [ ] 6. Fabrication
  - [ ] 6.1 Implement outline generation and SVG, DXF, and PDF exports with calibration square, scale bar, and assembly sheet. Block export when unscaled. Property test 5.
    - _Requirements: 8.1–8.4_

- [ ] 7. Verification
  - [ ] 7.1 Implement the verify analysis, verdict thresholds, and refuted re-ranking.
    - _Requirements: 9.1, 9.2, 9.3_

- [ ] 8. End-to-end
  - [ ] 8.1 Playwright test covering resurrection, tie group, disambiguation answer, re-rank, exports, repaired upload, and confirmed verdict on the flapping-wing fixtures.
    - _Requirements: 10.2, 10.3_
