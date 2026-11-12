import { v7 } from "uuid";

/**
 * A UUIDv7 generated in the application, for rows whose ID is needed before insert (for example
 * to build an object key). Rows inserted without an ID get one from Postgres' uuidv7() default.
 */
export function newId(): string {
  return v7();
}
