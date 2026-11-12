# Requirements: Workbench

## Introduction

The workbench is the product's interface: the public landing page, the cabinet of specimens, guided footage capture, analysis progress, the instrument-grade workbench where the fitted model overlays the video and can be simulated and edited, the resurrection view, exports, verification, sharing, and the public Proving Ground. It follows `steering/design-language.md` ("The Anatomist's Workshop") and must be good enough to compete for design awards, with accessibility and performance treated as part of the design.

## Glossary

- **Cabinet**: the list of a user's specimens.
- **Plate**: an engraved rendering of a mechanism, with a plate number and caption.
- **Ghost**: the ectoplasm rendering of a candidate or inferred part.
- **Revision**: an immutable saved state of a mechanism graph.

## Requirements

### Requirement 1: Design system

**User Story:** As a user, I want a distinctive, coherent interface, so that the product feels crafted and memorable.

#### Acceptance Criteria

1. THE design system in `packages/ui` SHALL implement the palette, typography, and motifs from the design language as tokens and components.
2. THE components SHALL be built on React Aria Components and SHALL be styled from scratch.
3. THE design system SHALL include: buttons, dial and vernier inputs paired with text fields, specimen tags, plate frames, callouts with leader lines, tabs, dialogs, toasts, menus, tooltips, data tables, timeline, empty states, error states, and skeleton states matching final layout.
4. THE design system SHALL be documented in a Storybook with visual regression tests on every component.
5. THE interface SHALL NOT use purple or violet hues, glassmorphism, emoji icons, or default component-library styles.

### Requirement 2: Landing page

**User Story:** As a first-time visitor or judge, I want to understand and feel the product in seconds, so that I want to try it.

#### Acceptance Criteria

1. THE landing page SHALL open on a full-bleed live engraved simulation of a real reconstructed mechanism that the visitor can turn by dragging.
2. THE landing page SHALL show a real before-and-after: broken footage, the ghost repair, and the verified repaired footage, from a real specimen processed by the pipeline.
3. THE landing page SHALL link to try a sample specimen without signing in, and to the Proving Ground.
4. THE landing page SHALL meet the performance budgets in the design language.

### Requirement 3: Sample specimens

**User Story:** As a judge, I want to explore real results without filming a machine, so that I can evaluate the product in minutes.

#### Acceptance Criteria

1. THE system SHALL provide public sample specimens processed by the real pipeline, stored and served as ordinary specimens owned by a system account and shared read-only.
2. THE user SHALL be able to duplicate a sample specimen into their own cabinet to edit, re-run, and resurrect it.

### Requirement 4: Cabinet

**User Story:** As a user, I want my specimens arranged clearly, so that I can return to any machine quickly.

#### Acceptance Criteria

1. THE cabinet SHALL show each specimen as a plate card with its cover frame, title, footage count, latest analysis state, and latest verification verdict.
2. THE user SHALL be able to create, rename, describe, duplicate, and delete specimens. Delete SHALL require confirmation and explain what is removed.
3. THE cabinet SHALL support search by title and filter by state.

### Requirement 5: Footage upload and guided capture

**User Story:** As a user with a phone next to the machine, I want guidance while filming, so that my footage works the first time.

#### Acceptance Criteria

1. THE user SHALL be able to upload footage by drag and drop or file picker with resumable progress, and assign its role (reference, broken, repaired, supplementary, archival).
2. ON mobile devices, THE web app SHALL offer guided capture using the camera through `getUserMedia` and `MediaRecorder`, with a framing guide, a live stillness meter from device motion and frame difference, an exposure warning, and a prompt to turn the crank through at least two full cycles.
3. THE footage list SHALL show probe results, rejection reasons with suggested fixes, and a playable proxy.
4. BEFORE starting an analysis, THE user SHALL see a trim control preloaded with the engine's suggested window (two to four cycles, at most 90 seconds) and SHALL be able to adjust it.
5. THE web app SHALL offer a printable marker sheet (PDF with ArUco tags at a stated size, colored dot stickers, and a scale ruler) and explain that markers make tracking faster and more exact and set real-world scale.

### Requirement 6: Analysis progress and input requests

**User Story:** As a user, I want to watch the reconstruction happen and answer questions quickly, so that waiting is informative.

#### Acceptance Criteria

1. THE analysis view SHALL show each stage with live progress over SSE, and SHALL show each stage's intermediate artifact as soon as it exists (stabilized preview, part masks, tracks, bodies, joints).
2. WHEN the engine raises an input request, THE view SHALL present it as a focused prompt on the relevant frame and region with the engine's preferred option preselected and its confidence shown.
3. THE user SHALL be able to cancel an analysis and SHALL see failures with the reason and a suggested action.
4. WHEN the user leaves and returns, THE view SHALL restore the current state from the server.
5. WHILE an analysis is queued, THE view SHALL show the queue position, estimated start and finish times, and the user's remaining daily allowance.
6. THE user SHALL be able to outline a part by tapping it or drawing a box on a frame, with the outline computed in the browser, refined by further taps, and submitted as a correction. WHEN the device is too slow for in-browser outlining, THE view SHALL offer polygon and brush tools instead.
7. THE view SHALL show, per body, how much of the clip was observed before and after model-guided re-tracking.

### Requirement 7: Workbench viewer

**User Story:** As a user, I want to see the fitted model on top of the video and next to an engraved plate, so that I can judge the reconstruction.

#### Acceptance Criteria

1. THE workbench SHALL show the proxy video with the model overlay and the engraved plate side by side, synchronized to one timeline.
2. THE timeline SHALL show the frame, the driver angle, singularity markers, occlusion bands, and per-body residual bands.
3. THE overlay SHALL draw bodies, joints with specimen tags, tracks (toggleable), and residual heat, and SHALL distinguish observed, inferred (sutures), user, and candidate (ghost) elements.
4. THE inspector SHALL show the selected body's or joint's parameters with uncertainty, confidence, and provenance.
5. THE workbench SHALL support keyboard navigation of frames, selection, and playback with documented shortcuts.

### Requirement 8: Model editing

**User Story:** As a user, I want to correct and modify the model directly, so that I can fix mistakes and explore changes.

#### Acceptance Criteria

1. THE user SHALL be able to drag joint anchors on the plate or video, enter exact values on instrument inputs, change joint kinds, add and remove bodies and joints, and change the driver.
2. WHEN the user edits, THE plate SHALL re-solve in the Web Worker and update within one frame for mechanisms up to 20 bodies.
3. WHEN an edit makes the mechanism unassemblable, THE workbench SHALL show the failing joints and the last valid state without discarding the edit.
4. THE workbench SHALL provide undo and redo, and SHALL save edits as revisions with an author and a summary.
5. THE user SHALL be able to view revision history, compare two revisions (parameter diff and overlaid plates), and restore any revision.
6. THE user SHALL be able to refit a revision to the footage, keeping their edits as priors or fixed values.

### Requirement 9: Simulation controls

**User Story:** As a user, I want to run the machine and study its motion, so that I understand how it works.

#### Acceptance Criteria

1. THE user SHALL be able to play, pause, step, and scrub the driver, and set the speed.
2. THE user SHALL be able to trace any point's path, show velocity vectors, and show transmission angles and singularity locations.
3. THE workbench SHALL show the mobility analysis and highlight free degrees of freedom when the model is underconstrained.

### Requirement 10: Resurrection view

**User Story:** As a restorer, I want to compare candidate repairs visually and numerically, so that I can choose with confidence.

#### Acceptance Criteria

1. THE view SHALL list candidates grouped by tie group, with rank, score breakdown, cognate labels, and plausibility indicators.
2. THE view SHALL draw the selected candidate as a ghost on the broken footage and on the plate, with its motion trail, and SHALL show its simulated output path against the target.
3. THE view SHALL support comparing two candidates side by side.
4. FOR tie groups, THE view SHALL present the disambiguation step as a clear instruction with an illustration of where to measure or what to film, and SHALL accept the answer inline.
5. THE user SHALL be able to promote a candidate to a regular revision and continue editing.

### Requirement 11: Export and verification

**User Story:** As a restorer, I want to print the part and confirm the repair, so that the loop from video to working machine closes.

#### Acceptance Criteria

1. THE export dialog SHALL preview the part template at true scale and let the user set thickness, hole diameter, margin, and format.
2. THE user SHALL be able to download SVG, DXF, and PDF exports and see past exports.
3. THE verification view SHALL show the repaired footage with the predicted ghost overlaid, the measured deviation, and the verdict.
4. WHEN the verdict is confirmed, THE view SHALL play the galvanic spark and show "It lives." (respecting reduced motion).

### Requirement 12: Sharing

**User Story:** As a user, I want to share a specimen, so that others can see the reconstruction and repair.

#### Acceptance Criteria

1. THE user SHALL be able to create, copy, and revoke read-only share links.
2. A shared specimen SHALL open in a read-only workbench without sign-in, with simulation controls enabled and editing disabled.
3. THE system SHALL provide an embeddable player for a specimen's plate and a generated Open Graph image of the plate.

### Requirement 13: Proving Ground page

**User Story:** As a judge, I want to see measured accuracy with real examples, so that I trust the claims.

#### Acceptance Criteria

1. THE Proving Ground SHALL present benchmark summaries by family, profile, and tier, trends across runs, and an honest list of weak areas, as specified in the synthetic-lab spec.
2. THE Proving Ground SHALL open any clip in a comparison view showing truth, reconstruction, and resurrection result.

### Requirement 14: Accessibility

**User Story:** As a user with a disability, I want to use every feature, so that the product is usable by everyone.

#### Acceptance Criteria

1. THE web app SHALL meet WCAG 2.2 AA.
2. EVERY canvas view SHALL have an accessible equivalent: a structured list of bodies and joints with values, keyboard selection, and live-region announcements for simulation state changes.
3. THE web app SHALL honor `prefers-reduced-motion` and `prefers-contrast`.
4. THE end-to-end suite SHALL fail on serious or critical axe violations.

### Requirement 15: Performance

**User Story:** As a user on ordinary hardware, I want the app to feel instant, so that it works in a workshop on a laptop or tablet.

#### Acceptance Criteria

1. THE web app SHALL meet the design-language budgets for LCP, INP, and CLS, enforced by Lighthouse CI.
2. THE plate renderer SHALL render at 60 fps for mechanisms up to 50 bodies on a mid-range laptop.
3. THE workbench SHALL start scrubbing within 1.5 seconds of opening a specimen on broadband, loading overlay chunks progressively.

### Requirement 16: Responsive layouts

**User Story:** As a user in a workshop, I want the app on a tablet and my phone, so that I can use it next to the machine.

#### Acceptance Criteria

1. THE workbench SHALL support desktop and tablet layouts with touch-friendly editing.
2. ON phones, THE web app SHALL support capture, upload, analysis progress, input requests, viewing, simulation, resurrection results, and verification, with editing presented in a simplified inspector.
