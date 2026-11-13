# Tasks: Workbench

- [ ] 1. Design system
  - [ ] 1.1 Implement tokens (palette, type scale, spacing, motion), fonts (IM Fell English, IBM Plex Sans Condensed, IBM Plex Mono, self-hosted with subsetting), and Tailwind 4 theme.
    - _Requirements: 1.1, 1.5_
  - [ ] 1.2 Build components on React Aria Components: buttons, dial and vernier inputs, specimen tags, plate frames, callouts, tabs, dialogs, toasts, menus, tooltips, tables, timeline, empty, error, and skeleton states.
    - _Requirements: 1.2, 1.3_
  - [ ] 1.3 Storybook with visual regression snapshots in both motion modes.
    - _Requirements: 1.4, 14.3_

- [ ] 2. Auth and account screens to the design language (with platform-foundation task 4.3).
  - _Requirements: 1.1_

- [ ] 3. Plate renderer
  - [ ] 3.1 Build the Three.js engraving shader (hatching, outline weight, paper), DOM label layer, and per-plane orthographic views.
    - _Requirements: 7.1, 15.2_
  - [ ] 3.2 Build ghost, suture, trace, velocity, and transmission-angle visuals.
    - _Requirements: 7.3, 9.2, 10.2_
  - [ ] 3.3 Performance test at 50 bodies, 60 fps.
    - _Requirements: 15.2_

- [ ] 4. Cabinet and specimens
  - [ ] 4.1 Add `mechanism`, `mechanism_revision`, and `specimen_sample` tables and migration with typed queries. Integration tests.
    - _Requirements: 4.1, 8.4_
  - [ ] 4.2 Build the cabinet and specimen overview with create, rename, describe, duplicate, delete, search, and filter. End-to-end tests.
    - Done: cabinet with create, rename, describe, delete, paging, empty, error, and loading states, and the specimen page with its footage, with end-to-end tests. Remaining: duplicate, search, filter, and the specimen overview's analysis and revision summaries (they arrive with those features).
    - _Requirements: 4.1, 4.2, 4.3_

- [ ] 5. Footage and capture
  - [ ] 5.1 Build upload UI on the platform uploader with role assignment, probe results, rejection guidance, and proxy playback.
    - Done: role assignment, resumable uploads with pause, resume, retry, and cancel, probe results, rejection guidance, playback of the original. Remaining: a normalized proxy for codecs the browser cannot play (comes with the vision pipeline's normalization).
    - _Requirements: 5.1, 5.3_
  - [ ] 5.1a Build the trim control with the suggested window and the printable marker sheet PDF (ArUco tags, colored dots, scale ruler).
    - _Requirements: 5.4, 5.5_
  - [ ] 5.2 Build guided capture with framing guide, stillness meter, exposure warning, and cycle counter. End-to-end test with fake camera stream.
    - _Requirements: 5.2, 16.2_

- [ ] 6. Analysis theatre
  - [ ] 6.1 Build live stage plates from SSE with progressive artifacts, input request prompts, cancel, failure states, state restore, queue position, ETA, allowance, and re-tracking gain per body. End-to-end test.
    - _Requirements: 6.1–6.5, 6.7_
  - [ ] 6.2 Build the part outlining tool on the browser segmentation worker, with the manual polygon and brush fallback and correction submission. End-to-end test with the WebAssembly backend.
    - _Requirements: 6.6_

- [ ] 7. Workbench viewer
  - [ ] 7.1 Build synchronized video, overlay, plate, and timeline with chunked overlay streaming.
    - _Requirements: 7.1, 7.2, 7.3, 15.3_
  - [ ] 7.2 Build the inspector with uncertainty and provenance, and keyboard shortcuts.
    - _Requirements: 7.4, 7.5_
  - [ ] 7.3 Build the specimen ledger accessible equivalent and live-region announcements.
    - _Requirements: 14.2_

- [ ] 8. Editing
  - [ ] 8.1 Implement the bench store with Immer patches, undo, redo, and Web Worker solving with failure states. Properties 1 and 4.
    - _Requirements: 8.1, 8.2, 8.3, 8.4_
  - [ ] 8.2 Implement save with optimistic concurrency, revision history, diff and overlaid compare, restore, and refit. Properties 2 and 3. End-to-end tests.
    - _Requirements: 8.4, 8.5, 8.6_

- [ ] 9. Simulation controls
  - [ ] 9.1 Implement playback, scrubbing, speed, traces, velocities, transmission angles, singularity markers, and mobility display.
    - _Requirements: 9.1, 9.2, 9.3_

- [ ] 10. Resurrection, export, verification
  - [ ] 10.1 Build the resurrection view with tie groups, breakdowns, ghost overlays, target path, side-by-side compare, inline disambiguation, and promote to revision.
    - _Requirements: 10.1–10.5_
  - [ ] 10.2 Build the export dialog with true-scale preview and export history.
    - _Requirements: 11.1, 11.2_
  - [ ] 10.3 Build the verification view with overlay, deviation, verdict, and the galvanic spark.
    - _Requirements: 11.3, 11.4_

- [ ] 11. Sharing and samples
  - [ ] 11.1 Build the read-only shared workbench, embed player, and Open Graph plate images.
    - _Requirements: 12.1, 12.2, 12.3_
  - [ ] 11.2 Process real sample specimens through the pipeline under the system account, publish them, and build `/samples` with duplicate-to-cabinet.
    - _Requirements: 3.1, 3.2_

- [ ] 12. Proving Ground UI
  - [ ] 12.1 Build summary, trends, weak-area list, and clip comparison views.
    - _Requirements: 13.1, 13.2_

- [ ] 13. Landing
  - [ ] 13.1 Build the live plate hero, the scroll story from real sample specimens, and calls to action. Lighthouse budgets.
    - _Requirements: 2.1–2.4, 15.1_

- [ ] 14. Responsive and accessibility pass
  - [ ] 14.1 Tablet and phone layouts with touch editing and simplified inspector.
    - _Requirements: 16.1, 16.2_
  - [ ] 14.2 WCAG 2.2 AA audit, `prefers-contrast` support, axe gating in end-to-end.
    - _Requirements: 14.1, 14.3, 14.4_
