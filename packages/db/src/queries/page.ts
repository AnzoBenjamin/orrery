/** Keyset pagination over UUIDv7 ids, newest first. */
export interface PageRequest {
  /** Maximum rows to return (1 to 100). */
  limit: number;
  /** Return rows older than this id (the `nextCursor` of the previous page). */
  before?: string | undefined;
}

export interface Page<T> {
  items: T[];
  /** Pass as `before` to fetch the next page; undefined on the last page. */
  nextCursor: string | undefined;
}

export const MAX_PAGE_SIZE = 100;

export function clampLimit(limit: number): number {
  if (!Number.isInteger(limit) || limit < 1)
    throw new RangeError("page limit must be a positive integer");
  return Math.min(limit, MAX_PAGE_SIZE);
}

/** Callers fetch `limit + 1` rows; the extra row only signals that another page exists. */
export function toPage<T extends { id: string }>(rows: T[], limit: number): Page<T> {
  const items = rows.slice(0, limit);
  const last = items.at(-1);
  return { items, nextCursor: rows.length > limit && last ? last.id : undefined };
}
