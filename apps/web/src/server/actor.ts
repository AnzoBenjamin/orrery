/** Who is calling (design: actors `user`, `share`, `admin`, `engine`). */
export type Actor =
  | { kind: "anonymous" }
  | {
      kind: "user";
      userId: string;
      /** The session the request came in on, so account settings can tell "this device" apart. */
      sessionId: string;
      emailVerified: boolean;
      isAdmin: boolean;
    }
  | { kind: "share"; specimenId: string; shareLinkId: string };

export const anonymous: Actor = { kind: "anonymous" };
