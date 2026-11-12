# Design: Workbench

## Overview

The web app is TanStack Start with file-based routes. Server state uses TanStack Query, hydrated from loaders and updated by SSE events. The editor state uses a Zustand store with Immer patches. The solver runs in a Web Worker through `SolverClient`. Rendering uses a custom WebGL engraving renderer for plates, and a 2D canvas plus WebGL overlay for video.

## Routes

| Route | Access | Content |
|---|---|---|
| `/` | public | landing with live plate and real before/after |
| `/samples` | public | sample specimens |
| `/proving-ground`, `/proving-ground/clips/$clipId` | public | benchmarks |
| `/s/$token` | share | read-only specimen |
| `/embed/$token` | share | embeddable plate player |
| `/sign-in`, `/sign-up`, `/verify`, `/reset` | public | auth |
| `/cabinet` | user | specimens |
| `/specimens/$id` | owner or share | overview: footage, analyses, mechanisms, runs |
| `/specimens/$id/capture` | owner | guided capture (mobile first) |
| `/specimens/$id/analyses/$analysisId` | owner or share | progress and input requests |
| `/specimens/$id/bench/$mechanismId` | owner or share | workbench |
| `/specimens/$id/resurrections/$runId` | owner or share | resurrection view |
| `/specimens/$id/verifications/$verificationId` | owner or share | verification |
| `/account` | user | settings |
| `/admin` | admin | operator page |

## Persistence owned by this spec

| Table | Columns |
|---|---|
| `mechanism` | id, specimen_id, name, origin (`fitted`, `edited`, `candidate`, `duplicated`), head_revision_id, created_at, updated_at |
| `mechanism_revision` | id, mechanism_id, parent_revision_id, graph jsonb (validated), uncertainty jsonb, graph_hash, author_kind (`engine`, `user`, `system`), author_id, summary, created_at |
| `specimen_sample` | specimen_id, slug, ordinal, published_at. Marks system-owned sample specimens |

Server functions: `listSpecimens`, `createSpecimen`, `updateSpecimen`, `duplicateSpecimen`, `deleteSpecimen`, `listMechanisms`, `getRevision`, `saveRevision` (optimistic concurrency on `head_revision_id`), `listRevisions`, `diffRevisions`, `restoreRevision`, `refitRevision`, `promoteCandidate`, `listSamples`, `getShareSpecimen`.

## Editor state

```ts
type BenchState = {
  revisionId: string;          // server head when loaded
  graph: Mechanism;            // working copy
  patches: { undo: Patch[][]; redo: Patch[][] };
  selection: { kind: "body" | "joint" | "point"; id: string } | null;
  frame: number; driver: number; playing: boolean; speed: number;
  overlays: { tracks: boolean; residuals: boolean; traces: string[]; velocities: boolean; transmission: boolean };
  solve: { status: "ok" | "failed"; failingJoints: string[]; lastValidPoses: Float64Array | null };
  dirty: boolean;
}
```

- Each edit produces Immer patches for undo and redo. Saving converts the working copy into a revision with a summary generated from the patch kinds (for example "Moved joint C; lengthened link B to 84.2 mm").
- Conflicts: if `head_revision_id` changed on the server, the user is shown both revisions and can rebase their working copy.

## Rendering

### Engraved plate renderer (`packages/ui/plate`)

- Three.js scene with an orthographic camera per plane. Body outlines become meshes with a custom shader:
  - Cross-hatching from screen-space line patterns oriented by a per-body angle, density driven by a lighting term (lamp position), so parts read as engraved metal or card.
  - Outline pass with variable line weight (thicker on the side away from the light).
  - Paper texture and slight ink bleed on the background.
- Ghost material: additive ectoplasm with fresnel-like edge glow, low-frequency flicker, and a fading motion trail built from the last N poses.
- Suture material: stitched dashes along inferred joints.
- Labels and callouts are DOM elements positioned from projected coordinates, so text is crisp and accessible.

### Video overlay

- Proxy video in a `<video>` element, frame-synchronized with `requestVideoFrameCallback`. Overlay canvas uses WebGL for tracks and residual heat, and 2D canvas for tags and leader lines.
- Overlay chunks (Arrow) streamed with `apache-arrow` and decoded in a worker.

### Timeline

- Canvas track lanes for driver angle, singularities, occlusion bands, residual bands. Keyboard: `J/K/L` play control, `,`/`.` frame step, `[`/`]` previous and next singularity.

## Key screens

### Landing

- Hero: the plate renderer running a reconstructed real specimen (Jansen leg or flapping wing). Dragging turns the crank, and the tags and callouts follow.
- Scroll story: broken footage → diagnosis findings appear as oxblood tags → the ghost repair flickers in → the verified footage plays with the spark → "It lives."
- Assets come from real sample specimens fetched through the same share endpoints as everything else.

### Part outlining

- A `SegmentationClient` wraps the browser segmentation worker from the vision-pipeline design (SAM 2.1 through transformers.js, WebGPU or WebAssembly). The encoder output for the current frame is cached so each tap only runs the decoder.
- The outline tool draws the live mask as an engraved hatch fill with a brass outline. Positive taps add, Alt-taps subtract, and the result is saved as a `part_mask` annotation.
- Workbench and analysis routes send `Cross-Origin-Opener-Policy: same-origin` and `Cross-Origin-Embedder-Policy: require-corp` so WebAssembly threads work. Garage serves the model weights with `Cross-Origin-Resource-Policy: cross-origin` and CORS for the app origin.
- Capability probe result is stored per device in local storage so the choice between the model and manual tools is made once.

### Guided capture

- Camera preview with a framing rectangle, stillness meter combining `DeviceMotionEvent` and frame differencing on a downscaled `OffscreenCanvas`, exposure warning from luminance histogram, a cycle counter that recognizes repeated motion locally, and a record button that saves through `MediaRecorder` into the resumable uploader.

### Analysis theatre

- Vertical list of stages as engraved plates that fill in as artifacts arrive: stabilized preview, masks, tracks (animated), bodies colored by tag, joints with sutures, final fit.
- Input requests take over the focused frame with options as tagged choices.

### Resurrection

- Left: candidates grouped by tie group. Each card shows rank, total, breakdown bars, cognate badge, plausibility marks.
- Center: broken footage with the ghost overlay. Right: plate with ghost and target path in parchment ink.
- Disambiguation: an illustrated instruction (for example a dimension callout between two holes with "Measure this distance") with an inline input.

## Accessibility

- Every canvas has a synchronized "specimen ledger": a table of bodies, joints, and parameters with editable fields that use the same store.
- Live region announcements: driver angle on step, solve failures, input requests, verdicts.
- Focus management in dialogs and input requests per React Aria.

## Error, empty, and loading states

- Every route defines these states in the design language: empty cabinet shows an engraved empty cabinet with a capture call to action; failed analyses show the stage, reason, and action; skeletons match final layout.

## Correctness properties

1. *For any* sequence of edits, applying all undo patches restores the loaded graph exactly, and redo restores the edited graph. **Validates: 8.4**
2. *For any* saved revision, the stored graph validates and its hash equals the hash of the canonical serialization. **Validates: 8.4, 8.5**
3. *For any* two revisions, the diff applied to the first yields the second. **Validates: 8.5**
4. *For any* edit, the plate shows either a valid assembly or the failing joints with the last valid poses, never a partial assembly. **Validates: 8.3**

## Testing strategy

- Vitest with fast-check for properties 1 to 3. Component tests with Testing Library.
- Storybook with Playwright visual snapshots for every component and both reduced-motion modes.
- End-to-end per route: landing interaction (drag turns the crank), sample duplicate, cabinet CRUD, guided capture with a fake camera stream fed from a fixture clip (Chromium `--use-file-for-fake-video-capture`), upload, analysis with input request, workbench edit, failing edit, undo, save, history diff, restore, refit, resurrection flow, export, verification spark, share link signed out, embed, Proving Ground.
- Lighthouse CI on `/`, `/samples`, `/proving-ground`, `/s/$token`.
