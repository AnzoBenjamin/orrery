const numerals: ReadonlyArray<[number, string]> = [
  [1000, "M"],
  [900, "CM"],
  [500, "D"],
  [400, "CD"],
  [100, "C"],
  [90, "XC"],
  [50, "L"],
  [40, "XL"],
  [10, "X"],
  [9, "IX"],
  [5, "V"],
  [4, "IV"],
  [1, "I"],
];

/** Roman numeral for plate numbers ("Plate XIV"). Defined for 1 to 3999. */
export function toRoman(value: number): string {
  if (!Number.isInteger(value) || value < 1 || value > 3999) {
    throw new RangeError(`toRoman: ${value} is outside 1 to 3999`);
  }
  let rest = value;
  let out = "";
  for (const [n, s] of numerals) {
    while (rest >= n) {
      out += s;
      rest -= n;
    }
  }
  return out;
}
