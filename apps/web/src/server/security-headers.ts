/**
 * Response security headers (requirement 12.1). The Content Security Policy allows scripts only
 * with this request's nonce ('strict-dynamic' lets them load the app's chunks), and reaches out
 * only to this origin and the object store, which the browser uploads to and plays footage from.
 */
export function securityHeaders(options: {
  nonce: string;
  objectStoreOrigin: string;
  production: boolean;
}): Record<string, string> {
  const { nonce, objectStoreOrigin, production } = options;
  const csp = [
    "default-src 'self'",
    `script-src 'nonce-${nonce}' 'strict-dynamic'`,
    // Vite injects component styles as <style> tags during development.
    production ? `style-src 'self' 'nonce-${nonce}'` : "style-src 'self' 'unsafe-inline'",
    // Progress bars and meters set widths in server-rendered style attributes.
    "style-src-attr 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self' data:",
    `media-src 'self' blob: ${objectStoreOrigin}`,
    // Uploads go straight to the object store; development adds Vite's hot-reload socket.
    `connect-src 'self' ${objectStoreOrigin}${production ? "" : " ws: wss:"}`,
    "worker-src 'self' blob:",
    "object-src 'none'",
    "base-uri 'none'",
    "form-action 'self'",
    "frame-ancestors 'none'",
  ];
  if (production) csp.push("upgrade-insecure-requests");
  return {
    "content-security-policy": csp.join("; "),
    "x-content-type-options": "nosniff",
    "referrer-policy": "strict-origin-when-cross-origin",
    "permissions-policy":
      "camera=(self), microphone=(), geolocation=(), payment=(), usb=(), interest-cohort=()",
    "cross-origin-opener-policy": "same-origin",
    ...(production ? { "strict-transport-security": "max-age=63072000; includeSubDomains" } : {}),
  };
}

/** 128 random bits, base64: a fresh CSP nonce for each response. */
export function createNonce(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return btoa(String.fromCharCode(...bytes));
}
