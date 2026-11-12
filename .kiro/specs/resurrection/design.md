# Design: Resurrection

## Overview

Resurrection runs as an engine job of kind `resurrect`, with `verify` and `export` as related kinds. The web app stores runs and candidates and presents them.

```
broken model + diagnosis ─┐
                          ├─► generate candidates ─► assembly filter ─► refine (parallel) ─► score ─► uncertainty sampling
target motion (aligned) ──┘                                                                         │
                                                                    tie groups + cognates ◄─────────┘
                                                                            │
                                                         disambiguation steps ─► ranking ─► persist
```

## Target motion

- `TargetMotion = { kind, outputs: [{ bodyId, pointId | localPoint, weight }], samples: { driver: number[], positions: Vec3[][] }, sourceRef }`.
- Same-machine reference: body correspondence from vision-pipeline diagnosis alignment.
- Different unit: correspondence by appearance and geometry, then similarity transform (Umeyama) on matched body anchors, and phase offset by cross-correlation of the driver signal.
- Traced path: the user draws or traces a curve. Without timing, scoring uses path shape only and labels timing as unconstrained.

## Candidate generation

- Anchor sites per body: empty holes (highest prior), existing anchors, and a Poisson-disk sample over the body outline interior at spacing proportional to body size (default 40 sites).
- Binary link candidates: all site pairs across the two bodies that need constraint, filtered by distance bounds from the observed range of motion (the link length must lie between the minimum and maximum site separation over the cycle).
- Slider, gear, belt candidates: kind-specific parameter seeds (gear ratio from observed angular velocity ratio in the reference, pitch radius from the remaining gear's outline).
- Two missing parts: enumerate non-isomorphic kinematic chains connecting the affected bodies, using a precomputed atlas of planar chains up to 8 bodies with mobility 1 (generated once by graph enumeration with isomorphism pruning via canonical labeling, `pynauty`). For each chain, sample anchor sites as above.
- Assembly filter: batch `orrery_kinematics.simulate` over the driver range, discarding `RangeIncomplete`.

## Refinement

- Unknowns: new part anchor coordinates and parameters. Existing body geometry is free within priors equal to its fitted uncertainty.
- Objective: weighted phase-aligned output error over the target samples, solved by the mechanism-core fitter with the target treated as observations.
- Hole snapping: compare snapped versus free fits with a likelihood-ratio test. Keep snapped unless the improvement is significant at p < 0.01.
- Parallelism: a process pool inside the `engine` container (one worker per core, the solver releases the GIL), in batches. Typical single-link search: about 1,600 site pairs, about 300 after filtering, refined in parallel.

## Scoring

```
score = w_motion · E_motion + w_timing · E_timing + Σ w_k · P_k − w_hole · holes_used − w_parsimony · parts_added
```

- `E_motion`: discrete Fréchet distance between candidate and target output paths divided by the target path's bounding-box diagonal.
- `E_timing`: RMSE of output position versus driver angle after phase alignment, normalized the same way.
- Penalties `P_k`: transmission angle shortfall below 30 degrees, collision duration fraction, branch or circuit change, length-to-width ratio above material limit, anchors outside material.
- Weights live in a versioned config. The default weights are tuned on the synthetic-lab `core` suite to maximize top-1 recovery and recorded with the suite hash.

## Uncertainty, ties, cognates

- Draw 64 samples of existing-body geometry and target alignment from their covariances. Re-score each candidate per sample (simulation only, no refit). Each candidate gets a score distribution.
- Tie groups: candidates whose probability of being better than the leader exceeds 10% join the leader's group (pairwise over samples). Grouping repeats for the remainder.
- Cognates: candidates whose output motion agrees within a tolerance at every sampled driver value across the full cycle, but whose topology or anchors differ. For four-bars, cognate checking also computes the Roberts–Chebyshev cognates of the leader analytically, so their presence can be confirmed even when sampling missed them.

## Disambiguation

- For each tie group, compute pairwise prediction differences over all named points of all bodies and all driver angles. Also compute the differences in static distances between named points (measurable with a ruler).
- Candidate steps and costs: ruler measurement (cost 1), clip at a named crank angle of a named region (cost 2), clip from another viewpoint (cost 3).
- Choose the cheapest step whose expected difference exceeds 3× the measurement noise for every pair in the group.
- Answers arrive as `annotation` rows (measurement) or new footage (clip), triggering a re-rank job.

## Fabrication

- Outline: capsule with end margin around each hole, or the user can choose a straight bar with chamfers. Holes at true scale with user hole diameter.
- SVG and DXF (`ezdxf`, R2018, millimeters, layers `CUT`, `HOLES`, `ENGRAVE`). PDF with `reportlab`: 1:1 template, 50 mm calibration square, scale bar, assembly sheet with an engraved illustration rendered from the same renderer used in the workbench.

## Verification

- A `verify` analysis fits the repaired footage, aligns it to the candidate prediction, and computes the same motion and timing errors.
- Verdict thresholds: `confirmed` when both errors are within the fit noise level plus 2%, `partial` within 10%, otherwise `refuted`. The thresholds are recorded with the verification.
- Refuted verifications add the repaired footage as evidence and enqueue a re-rank that excludes the refuted candidate.

## Persistence

| Table | Columns |
|---|---|
| `resurrection_run` | id, specimen_id, broken_revision_id, target jsonb, outputs jsonb, status, params jsonb, weights_version, created_at, finished_at, error jsonb |
| `repair_candidate` | id, run_id, rank, revision_id (candidate graph stored as a mechanism revision with status `candidate`), total_score, breakdown jsonb, score_samples real[], tie_group, cognate_group, plausibility jsonb |
| `tie_group` | id, run_id, ordinal, reason, disambiguation jsonb |
| `disambiguation_answer` | id, tie_group_id, kind (`measurement`, `clip`), annotation_id, footage_id, created_at |
| `repair_export` | id, candidate_id, format, params jsonb, status, object_key, created_at |
| `verification` | id, candidate_id, footage_id, analysis_id, verdict, metrics jsonb, thresholds jsonb, created_at |

Server functions: `startResurrection`, `getResurrection`, `listResurrections`, `answerDisambiguation`, `createRepairExport`, `getRepairExportUrl`, `startVerification`, `getVerification`.

## Correctness properties

1. *For any* synthetic breakage of one binary link with a reference target on the `clean` tier, the true repair is in the top 3 and in the first tie group. **Validates: 2.2, 3.1, 4.1**
2. *For any* four-bar breakage, the analytic Roberts–Chebyshev cognates of the true repair, when anchorable on the available bodies, are grouped as cognates of it. **Validates: 6.2**
3. *For any* tie group, the proposed disambiguation step separates all pairs by at least 3× measurement noise in the ground truth simulation. **Validates: 7.1, 7.2**
4. *For any* candidate, the breakdown components sum to the total score. **Validates: 5.3**
5. *For any* exported template, hole center distances in the DXF equal the candidate's link length within 0.01 mm. **Validates: 8.1, 8.2**
6. *For any* target and candidate, motion error is invariant to the target's phase offset. **Validates: 4.1**

## Testing strategy

- Synthetic-lab metrics for properties 1 to 3 with baselines.
- Hypothesis tests for properties 4 to 6.
- Integration tests for every server function and table.
- End-to-end: on the broken flapping-wing fixture, start resurrection, see ranked candidates with a tie group and a disambiguation instruction, answer with a ruler measurement, see the re-ranked result, export the DXF and PDF and verify their contents, upload the repaired fixture, and see the `confirmed` verdict.
