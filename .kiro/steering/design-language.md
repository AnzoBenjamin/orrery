---
inclusion: always
---

# Design language: "The Anatomist's Workshop"

Orrery should feel like a nineteenth-century workshop at midnight where dead machines are dissected and brought back to life. The look is engraved plates, brass instruments, bone-colored paper, and lamp light. The spooky element is restraint plus a single uncanny effect: the spectral "ghost" of a missing part.

## What to avoid

- Purple or violet gradients, neon glows, glassmorphism, generic dark-mode SaaS cards.
- Default component-library styling (shadcn defaults, stock Tailwind palette).
- Emoji as icons, stock Halloween clip art (pumpkins, cartoon ghosts, bats), dripping-blood fonts.
- Decorative motion that delays the user.

## Palette

| Token | Hex | Use |
|---|---|---|
| `lampblack` | `#0E0D0B` | page background |
| `soot` | `#1A1814` | panels |
| `umber` | `#2A251E` | raised surfaces, borders |
| `bone` | `#E8DFC9` | primary text, engraving lines on dark |
| `parchment` | `#CDBF9F` | secondary text, plate backgrounds |
| `brass` | `#A8854A` | primary interactive, instrument dials |
| `brass-bright` | `#D4AF6A` | focus, active states |
| `oxblood` | `#7A231C` | destructive, errors, broken parts |
| `verdigris` | `#4F7F6F` | success, verified, fitted joints |
| `ectoplasm` | `#C8F2D8` | ghost candidates only, with low-opacity bloom |

All text and interactive states meet WCAG 2.2 AA contrast. Ectoplasm is reserved for inferred and candidate parts so the user always knows what is real and what is proposed.

## Typography (all SIL Open Font License)

- Display: IM Fell English and IM Fell English SC for titles, plate headings, and numerals in Roman form ("Plate XIV").
- Interface: IBM Plex Sans Condensed for labels, controls, body text.
- Instruments: IBM Plex Mono for measurements, coordinates, scores, tabular numerals.

## Motifs

- Engraved plates: the simulation renders with a cross-hatching shader in the style of *507 Mechanical Movements*. Each mechanism view has a plate number and caption.
- Callouts: measurements use leader lines and engraved dimension arrows.
- Specimen tags: bodies and joints are labeled with tied paper tags (letters A, B, C as in period engineering plates).
- Sutures: joints the engine inferred, not observed, render with stitched seams.
- Ghosts: candidate repair parts render in ectoplasm with a slow, subtle flicker and a faint trail of their motion path.
- Galvanic spark: when a verification confirms a repair, a short electrical arc animates across the repaired joint. The confirmed state reads "It lives."
- Lamp light: a slow, low-amplitude vignette flicker and film grain on hero surfaces only. Never on dense working areas.
- Brass instruments: numeric inputs that matter (crank angle, link length) are dials or vernier sliders, always paired with a typed field.

## Motion and sound

- Motion communicates state: mechanisms animate because they are being simulated, not for decoration.
- Respect `prefers-reduced-motion`: disable flicker, grain, and spark, keep state changes as cross-fades.
- Optional sound (off by default): clockwork tick while simulating, spark on verification.

## Layout

- The workbench is an instrument: video and engraved simulation side by side, timeline beneath, inspector to the right. Dense, precise, no wasted chrome.
- Marketing and landing surfaces are cinematic: a full-bleed live simulation of an engraved mechanism that the visitor can turn by dragging.

## Performance budgets

- LCP under 2.0 s on the landing page (4G, mid-range phone).
- INP under 200 ms everywhere. Simulation rendering at 60 fps for mechanisms up to 50 bodies on a mid-range laptop.
- CLS under 0.05.
