/**
 * Design tokens for "The Anatomist's Workshop" (.kiro/steering/design-language.md).
 * styles.css declares the same values for Tailwind; test/tokens.test.ts keeps them in sync and
 * checks WCAG 2.2 AA contrast for every pairing the components use.
 */
export const palette = {
  lampblack: "#0E0D0B",
  soot: "#1A1814",
  umber: "#2A251E",
  bone: "#E8DFC9",
  parchment: "#CDBF9F",
  brass: "#A8854A",
  brassBright: "#D4AF6A",
  oxblood: "#7A231C",
  verdigris: "#4F7F6F",
  ectoplasm: "#C8F2D8",
} as const;

export type PaletteToken = keyof typeof palette;

/**
 * Foreground and background pairings used for text and interactive states, with the minimum
 * contrast ratio each must meet (4.5 for text, 3 for large text and non-text UI per WCAG 2.2 AA).
 */
export const contrastPairs: ReadonlyArray<{
  use: string;
  fg: PaletteToken;
  bg: PaletteToken;
  min: number;
}> = [
  { use: "body text on page", fg: "bone", bg: "lampblack", min: 4.5 },
  { use: "body text on panel", fg: "bone", bg: "soot", min: 4.5 },
  { use: "secondary text on page", fg: "parchment", bg: "lampblack", min: 4.5 },
  { use: "secondary text on panel", fg: "parchment", bg: "soot", min: 4.5 },
  { use: "secondary text on raised surface", fg: "parchment", bg: "umber", min: 4.5 },
  { use: "brass link text on panel", fg: "brass", bg: "soot", min: 4.5 },
  { use: "primary button label", fg: "lampblack", bg: "brass", min: 4.5 },
  { use: "primary button label, active", fg: "lampblack", bg: "brassBright", min: 4.5 },
  { use: "focus ring against panel", fg: "brassBright", bg: "soot", min: 3 },
  { use: "input border against panel", fg: "brass", bg: "soot", min: 3 },
  { use: "error text on oxblood banner", fg: "bone", bg: "oxblood", min: 4.5 },
  { use: "success border against panel", fg: "verdigris", bg: "soot", min: 3 },
  { use: "ink on paper plate", fg: "lampblack", bg: "bone", min: 4.5 },
  { use: "soft ink on paper plate", fg: "umber", bg: "bone", min: 4.5 },
  { use: "correction ink (errors, focus) on paper", fg: "oxblood", bg: "bone", min: 4.5 },
  { use: "paper button label on hovered oxblood", fg: "bone", bg: "oxblood", min: 4.5 },
  { use: "specimen tag lettering", fg: "lampblack", bg: "parchment", min: 4.5 },
  { use: "ghost part against the desk", fg: "ectoplasm", bg: "lampblack", min: 3 },
  { use: "brass-bright link text on raised surface", fg: "brassBright", bg: "umber", min: 4.5 },
];

/**
 * Pairings that fail AA and must not be used for text. Oxblood and verdigris are too dark to be
 * read on the dark surfaces, so errors put bone text on an oxblood fill and success marks a
 * verdigris border beside bone text. Brass text on umber is just short of 4.5:1.
 */
export const forbiddenTextPairs: ReadonlyArray<{ fg: PaletteToken; bg: PaletteToken }> = [
  { fg: "oxblood", bg: "soot" },
  { fg: "oxblood", bg: "lampblack" },
  { fg: "verdigris", bg: "soot" },
  { fg: "brass", bg: "umber" },
  { fg: "brass", bg: "bone" },
  { fg: "verdigris", bg: "bone" },
];

export const fonts = {
  display: '"IM Fell English", "Iowan Old Style", Georgia, serif',
  displaySmallCaps: '"IM Fell English SC", "IM Fell English", Georgia, serif',
  interface: '"IBM Plex Sans Condensed", "Arial Narrow", system-ui, sans-serif',
  instrument: '"IBM Plex Mono", ui-monospace, monospace',
} as const;
