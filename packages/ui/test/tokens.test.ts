import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { contrastRatio } from "../src/contrast.ts";
import { contrastPairs, forbiddenTextPairs, palette } from "../src/tokens.ts";

const css = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8");
const kebab = (s: string) => s.replace(/[A-Z]/g, (c) => `-${c.toLowerCase()}`);

describe("design tokens", () => {
  it("declares every palette colour in styles.css with the same value", () => {
    for (const [name, hex] of Object.entries(palette)) {
      expect(css.toLowerCase()).toContain(`--color-${kebab(name)}: ${hex.toLowerCase()};`);
    }
  });

  it.each(contrastPairs)("$use meets $min:1 ($fg on $bg)", ({ fg, bg, min }) => {
    expect(contrastRatio(palette[fg], palette[bg])).toBeGreaterThanOrEqual(min);
  });

  it.each(forbiddenTextPairs)(
    "$fg on $bg is correctly listed as below AA text contrast",
    ({ fg, bg }) => {
      expect(contrastRatio(palette[fg], palette[bg])).toBeLessThan(4.5);
    },
  );

  it("computes the WCAG reference ratios", () => {
    expect(contrastRatio("#000000", "#FFFFFF")).toBeCloseTo(21, 5);
    expect(contrastRatio("#777777", "#FFFFFF")).toBeCloseTo(4.48, 2);
  });
});
