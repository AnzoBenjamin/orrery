/**
 * Accepts only same-origin, absolute paths as post-sign-in destinations, so a crafted link cannot
 * send a user to another site ("//evil.example", "/\\evil.example", and "https://..." are rejected).
 */
export function safeRedirect(target: string | undefined, fallback = "/"): string {
  if (target === undefined) return fallback;
  // Browsers strip tabs and newlines from URLs, so "/\t/evil" would become "//evil".
  const hasControlCharacter = [...target].some((c) => (c.codePointAt(0) ?? 0) < 0x20);
  const sameOriginPath = /^\/(?![/\\])/.test(target) && !hasControlCharacter;
  return sameOriginPath ? target : fallback;
}
