import type { FootageRoleName } from "../server/operations/footage.ts";

/** How each footage role is named and explained in the interface. */
export const footageRoles: Record<FootageRoleName, { label: string; hint: string }> = {
  reference: {
    label: "Working",
    hint: "The machine moving as it should: the motion a repair must restore.",
  },
  broken: {
    label: "Broken",
    hint: "The machine failing: seized, slipping, or with a part missing.",
  },
  repaired: {
    label: "Repaired",
    hint: "After your repair, filmed the same way, to verify the prediction.",
  },
  supplementary: {
    label: "Another angle",
    hint: "The same motion from a second viewpoint or closer in.",
  },
  archival: {
    label: "Archival film",
    hint: "Historical footage of this machine or one like it.",
  },
};

export const footageRoleOrder: readonly FootageRoleName[] = [
  "reference",
  "broken",
  "repaired",
  "supplementary",
  "archival",
];
