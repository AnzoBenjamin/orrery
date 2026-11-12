import fc from "fast-check";
import { describe, expect, it } from "vitest";
import { toRoman } from "../src/roman.ts";

const fromRoman = (s: string) => {
  const v: Record<string, number> = { I: 1, V: 5, X: 10, L: 50, C: 100, D: 500, M: 1000 };
  let total = 0;
  for (let i = 0; i < s.length; i += 1) {
    const cur = v[s[i] as string] ?? 0;
    const next = v[s[i + 1] as string] ?? 0;
    total += cur < next ? -cur : cur;
  }
  return total;
};

describe("toRoman", () => {
  it("writes plate numbers", () => {
    expect([1, 4, 9, 14, 40, 90, 400, 1868, 3999].map(toRoman)).toEqual([
      "I",
      "IV",
      "IX",
      "XIV",
      "XL",
      "XC",
      "CD",
      "MDCCCLXVIII",
      "MMMCMXCIX",
    ]);
  });

  it("round-trips every value from 1 to 3999 in canonical form", () => {
    fc.assert(
      fc.property(fc.integer({ min: 1, max: 3999 }), (n) => {
        const r = toRoman(n);
        expect(fromRoman(r)).toBe(n);
        expect(r).not.toMatch(/IIII|XXXX|CCCC|VV|LL|DD/);
      }),
    );
  });

  it("rejects values outside the range", () => {
    expect(() => toRoman(0)).toThrow(RangeError);
    expect(() => toRoman(4000)).toThrow(RangeError);
    expect(() => toRoman(2.5)).toThrow(RangeError);
  });
});
