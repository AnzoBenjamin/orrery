---
inclusion: always
---

# Orrery: product context

## One line

Orrery turns video of an old or broken machine into an editable, simulated mechanism, infers the parts that are missing, ranks candidate repairs by how well they restore the original motion, and produces templates to fabricate the replacement.

## Hackathon context

- Event: Kiroween 2026 (Devpost). Deadline: Friday, December 4, 2026, 2:00 PM Pacific.
- Primary category: Resurrection (bringing dead machines back to life). Frankenstein is the alternate.
- Also targeting: Best Demo, Bonus Blog Prize, Social Blitz.
- Judging criteria: Potential Impact, Technological Implementation (depth of Kiro use), Design, Innovation/Idea, Presentation.
- Submission requirements that affect the codebase: public GitHub repo, OSI license detectable by GitHub, `/.kiro` committed at the repo root (never gitignored), a working hosted app, and a demo video under 3 minutes.

## Users

- Restorers of antique machines: sewing machines, typewriters, clocks, automata, looms, toys.
- Museum conservators documenting and reconstructing mechanisms.
- Maintainers of legacy industrial equipment whose drawings are lost.
- Engineering and STEM educators teaching kinematics with real objects.
- Makers and kinetic artists building automata.

## Core journey

1. Create a project for a machine (a "specimen").
2. Upload or capture footage: reference (working), broken, supplementary angles, archival film.
3. The engine reconstructs a mechanism model: bodies, joints, driver, geometry, with uncertainty.
4. The user inspects the model overlaid on the video, corrects it, edits it, and simulates it.
5. For broken footage, the engine diagnoses what is missing and proposes ranked repairs, including ties and cognates.
6. The user exports a repair template (SVG, DXF, or PDF at true scale), fabricates the part, films the repaired machine, and the engine verifies the prediction.

## Hosting constraint

Production is one CPU-only VPS with no GPU. Every feature must run within the budgets in `tech.md`. GPU-class work is replaced by model-constrained classical vision on the server or moved into the visitor's browser. Lab suites run off the VPS.

## Product principles

- The AI proposes and the solver checks. Every hypothesis (from vision models, VLMs, or users) must be checked against observed motion by the kinematics solver before it is shown as a result.
- Show uncertainty honestly. Display confidence and ties. Never present a single answer the evidence cannot support.
- When the engine is unsure, ask the user a specific question instead of guessing.
- Every capability is a complete product feature, never a demo path. See `quality.md`.

## Spec map and build order

Specs live in `.kiro/specs/`. Build in this order. Each phase ends with a deployable product.

| Order | Spec | Window |
|---|---|---|
| 1 | `platform-foundation` | Nov 13–15 |
| 2 | `mechanism-core` | Nov 13–17 (parallel with 1) |
| 3 | `synthetic-lab` | Nov 14–18 |
| 4 | `vision-pipeline` | Nov 16–22 |
| 5 | `resurrection` | Nov 19–24 |
| 6 | `workbench` | Nov 15–26 (continuous) |

Specs to be written once phase 1 to 6 learnings are in (Nov 21–26), with the schema already prepared for them:

- `spatial-reconstruction`: multi-view and feed-forward 3D reconstruction (VGGT-Omega / MapAnything class models), decomposition of 3D machines into planar subsystems, spatial joints.
- `mechanism-atlas`: topology library encoded from *507 Mechanical Movements* (Brown, 1868, public domain) and Cornell KMODDL Reuleaux models, VLM topology proposals, patent-drawing ingestion.
- `archival-footage`: historical film handling (flicker, gate weave, frame-rate ambiguity), reconstruction of machines that no longer exist.
- `dynamics`: optional mass, inertia, and spring estimation for force-dependent timing (escapements, flywheels).

Week 3 (Nov 27 – Dec 3): limits review, hardening, demo production, write-ups.
