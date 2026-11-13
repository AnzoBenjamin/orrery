/** Who is calling (design: actors `user`, `share`, `admin`, `engine`). */
export type Actor =
  | { kind: "anonymous" }
  | { kind: "user"; userId: string; emailVerified: boolean; isAdmin: boolean }
  | { kind: "share"; specimenId: string; shareLinkId: string };

export const anonymous: Actor = { kind: "anonymous" };
