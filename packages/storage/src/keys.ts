/**
 * Object keys. Every stored object lives under its owner and specimen (requirement 6.4), so a
 * key alone says whose data it is, and deleting a user or specimen can be checked by prefix.
 */

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

function assertId(name: string, value: string): void {
  if (!UUID.test(value)) throw new Error(`${name} must be a lowercase UUID`);
}

/**
 * The extension to store a file under: the original's, if it is short and alphanumeric, or
 * `bin`. The user's file name never appears in the key, so it cannot inject path segments.
 */
export function storedExtension(filename: string): string {
  const match = /\.([A-Za-z0-9]{1,8})$/.exec(filename.trim());
  return match?.[1] ? match[1].toLowerCase() : "bin";
}

export function specimenPrefix(input: { userId: string; specimenId: string }): string {
  assertId("userId", input.userId);
  assertId("specimenId", input.specimenId);
  return `users/${input.userId}/specimens/${input.specimenId}/`;
}

export function footageObjectKey(input: {
  userId: string;
  specimenId: string;
  footageId: string;
  filename: string;
}): string {
  assertId("footageId", input.footageId);
  return `${specimenPrefix(input)}footage/${input.footageId}.${storedExtension(input.filename)}`;
}
