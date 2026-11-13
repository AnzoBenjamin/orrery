/** Upload limits (requirement 6.3) and the multipart part size. */

/** Largest accepted footage file: 1 GB. */
export const MAX_FOOTAGE_BYTES = 1_000_000_000;

/** Longest accepted footage: 5 minutes. Checked by the engine's probe. */
export const MAX_FOOTAGE_DURATION_S = 300;

/** How long an unfinished multipart upload may stay open (requirement 6.6). */
export const UPLOAD_TTL_SECONDS = 24 * 60 * 60;

const MIB = 1024 * 1024;
/** S3 requires every part but the last to be at least 5 MiB, and allows at most 10,000 parts. */
export const MIN_PART_BYTES = 5 * MIB;
export const MAX_PARTS = 10_000;
/**
 * Preferred part size. Small enough that an interrupted phone upload loses little work, large
 * enough that a 1 GB file needs about 120 requests.
 */
export const PREFERRED_PART_BYTES = 8 * MIB;

/** The part size for a file, a whole number of MiB that keeps the part count within S3's limit. */
export function partSizeFor(byteSize: number): number {
  if (!Number.isInteger(byteSize) || byteSize < 0) {
    throw new RangeError("byteSize must be a non-negative integer");
  }
  const needed = Math.ceil(byteSize / MAX_PARTS / MIB) * MIB;
  return Math.max(PREFERRED_PART_BYTES, MIN_PART_BYTES, needed);
}

/** Number of parts a file of `byteSize` uploads in, at least one. */
export function partCount(byteSize: number, partSize: number): number {
  return Math.max(1, Math.ceil(byteSize / partSize));
}
