# Requirements: Resurrection

## Introduction

Resurrection infers the parts missing from a broken mechanism and ranks candidate repairs by how well they restore the target motion and how physically plausible they are. It reports ties and kinematically equivalent repairs (cognates) honestly, tells the user what extra evidence would separate tied candidates, produces fabrication templates for the chosen repair, and verifies the repair against new footage of the repaired machine.

## Glossary

- **Target motion**: the motion the repaired mechanism should reproduce.
- **Candidate**: a proposed repair (added bodies and joints) with its simulated motion and scores.
- **Tie group**: candidates whose scores are not separable given the evidence's uncertainty.
- **Cognate**: a different linkage that produces the same output motion (for example Roberts–Chebyshev cognates of a four-bar coupler curve).
- **Disambiguation step**: an action (a measurement or a specific clip) that would separate tied candidates.
- **Verification**: comparing footage of the repaired machine to the chosen candidate's prediction.

## Requirements

### Requirement 1: Target motion sources

**User Story:** As a restorer, I want to define the target motion from whatever evidence I have, so that I can repair machines without footage of them working.

#### Acceptance Criteria

1. THE system SHALL accept as target motion: a fitted model from reference footage of the same machine, a fitted model from footage of another unit of the same model, a path traced by the user over a frame or drawn on the canvas, or a mechanism revision.
2. WHEN the target comes from a different unit or video, THE system SHALL align it to the broken mechanism by matching bodies and estimating a similarity transform and phase offset.
3. THE user SHALL be able to choose which bodies and points are outputs to match (for example a wing tip), with weights.
4. WHEN no target motion is available, THE system SHALL rank candidates by plausibility only and SHALL label the result as unconstrained by motion evidence.

### Requirement 2: Candidate generation

**User Story:** As a restorer, I want the system to consider every reasonable way the missing part could attach, so that the true repair is not overlooked.

#### Acceptance Criteria

1. THE system SHALL use diagnosis findings (loose bodies, empty holes, missing joints) to determine which bodies need new constraints.
2. FOR a missing binary link, THE system SHALL generate candidates over pairs of anchor sites drawn from empty holes, existing anchor points, and a sampled grid over each body's outline.
3. FOR missing sliders, gears, and belts, THE system SHALL generate candidates using the corresponding joint kinds with parameters seeded from observed geometry (for example gear ratio from pitch circles on the remaining gear).
4. FOR up to two missing parts, THE system SHALL enumerate kinematic chain topologies with mobility matching the target and generate candidates for each.
5. THE system SHALL discard candidates that cannot assemble over the target driver range before scoring.

### Requirement 3: Candidate refinement

**User Story:** As a restorer, I want each candidate optimized before comparison, so that rankings reflect the best version of each repair.

#### Acceptance Criteria

1. THE system SHALL refine each surviving candidate's continuous parameters by minimizing motion error with the mechanism-core fitter, holding the existing bodies' fitted geometry within its uncertainty.
2. THE system SHALL keep anchors snapped to empty holes when the refinement does not significantly improve the fit by leaving them.
3. THE system SHALL run refinement in parallel and SHALL complete a single-missing-link search on a typical specimen within 60 seconds.

### Requirement 4: Motion scoring

**User Story:** As a restorer, I want candidates ranked by how closely they restore the original motion, so that the best repair is at the top.

#### Acceptance Criteria

1. THE system SHALL compute motion error between candidate and target output paths over a full cycle after optimal phase alignment.
2. THE system SHALL use discrete Fréchet distance and phase-aligned RMSE, normalized by the output path's extent, and SHALL report both.
3. THE system SHALL compare timing (output position as a function of driver angle), not only path shape, and SHALL report the two separately.

### Requirement 5: Plausibility scoring

**User Story:** As a restorer, I want physically unrealistic repairs penalized, so that the top candidate is buildable.

#### Acceptance Criteria

1. THE system SHALL penalize candidates for minimum transmission angle below 30 degrees, collisions, branch or circuit changes during the cycle, extreme length-to-width ratios, and anchors outside material.
2. THE system SHALL reward anchors at empty holes and repairs with fewer added parts.
3. THE system SHALL present the score as a decomposed breakdown that sums to the total.

### Requirement 6: Ties and cognates

**User Story:** As a restorer, I want to know when several repairs fit equally well, so that I do not trust a false single answer.

#### Acceptance Criteria

1. THE system SHALL estimate score uncertainty by propagating fit uncertainty (sampling parameters from their covariance) and SHALL group candidates whose score distributions overlap beyond a threshold into tie groups.
2. THE system SHALL detect cognates by comparing simulated output motion across the full cycle within tolerance and SHALL label them as producing identical output motion.
3. THE ranking SHALL show tie groups as groups, with the reason for the tie.

### Requirement 7: Disambiguation guidance

**User Story:** As a restorer, I want to know the quickest way to break a tie, so that I can resolve it with one measurement or one short clip.

#### Acceptance Criteria

1. FOR each tie group, THE system SHALL compute where the candidates' predictions differ most: which body, which point, and which driver angle.
2. THE system SHALL propose the cheapest disambiguation step: a ruler measurement between two named points, a clip of a named body at a named crank angle, or a view from a named direction.
3. WHEN the user provides the measurement or clip, THE system SHALL update the ranking with the new evidence.

### Requirement 8: Fabrication output

**User Story:** As a restorer, I want a printable template for the replacement part, so that I can make it.

#### Acceptance Criteria

1. THE system SHALL generate the replacement part's outline with hole positions at true scale, with user-set material thickness, hole diameter, and end margin.
2. THE system SHALL export SVG, DXF (via ezdxf), and a PDF with a printed scale bar and a calibration square for printer verification.
3. THE export SHALL include an assembly sheet naming which holes on which existing parts the new part attaches to, with an engraved-plate illustration.
4. WHEN the specimen is unscaled, THE system SHALL block fabrication export and ask the user to set scale.

### Requirement 9: Verification

**User Story:** As a restorer, I want to film the repaired machine and see whether the prediction was right, so that I know the repair worked.

#### Acceptance Criteria

1. WHEN the user uploads footage marked repaired and links it to a candidate, THE system SHALL run a verify analysis and compare the fitted motion with the candidate's prediction.
2. THE system SHALL report a verdict of `confirmed`, `partial`, or `refuted` with the motion error, and highlight where motion deviates.
3. WHEN refuted, THE system SHALL fold the new footage into the evidence and re-rank remaining candidates.

### Requirement 10: Persistence and presentation

**User Story:** As a restorer, I want resurrection runs saved with their evidence, so that I can return to them and share them.

#### Acceptance Criteria

1. THE system SHALL persist resurrection runs, candidates, score breakdowns, tie groups, disambiguation steps, exports, and verifications.
2. THE web app SHALL present each run with the candidate ranking, ghost overlays on the broken footage, side-by-side simulation against the target, and score breakdowns (UI in the workbench spec).
3. EVERY persisted entity in this spec SHALL have server functions with authorization and integration tests, and SHALL appear in the UI with end-to-end tests.
