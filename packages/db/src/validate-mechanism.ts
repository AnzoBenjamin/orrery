/**
 * Validation helper for mechanism graphs stored in jsonb columns.
 *
 * This ensures that any mechanism graph written to the database
 * conforms to the shared Zod schema from packages/schema.
 */
import { type Mechanism, mechanismSchema } from "@orrery/schema";

export type MechanismValidationError = {
  success: false;
  errors: Array<{
    path: (string | number | symbol)[];
    message: string;
    code: string;
  }>;
};

export type MechanismValidationSuccess = {
  success: true;
  data: Mechanism;
};

export type MechanismValidationResult = MechanismValidationSuccess | MechanismValidationError;

/**
 * Validate a mechanism graph against the schema.
 *
 * @param data - The mechanism graph data to validate (typically from a jsonb column)
 * @returns A result object with either validated data or structured errors
 *
 * @example
 * ```ts
 * const result = validateMechanism(someJsonData);
 * if (result.success) {
 *   // result.data is a validated Mechanism
 *   await db.insert(mechanismRevision).values({
 *     graph: result.data,
 *     // ...
 *   });
 * } else {
 *   // result.errors contains structured validation errors
 *   throw new Error(`Invalid mechanism: ${result.errors[0].message}`);
 * }
 * ```
 */
export function validateMechanism(data: unknown): MechanismValidationResult {
  const result = mechanismSchema.safeParse(data);

  if (result.success) {
    return {
      success: true,
      data: result.data,
    };
  }

  return {
    success: false,
    errors: result.error.issues.map((err) => ({
      path: err.path,
      message: err.message,
      code: err.code,
    })),
  };
}

/**
 * Assert that a mechanism graph is valid, throwing an error if not.
 *
 * @param data - The mechanism graph data to validate
 * @returns The validated mechanism
 * @throws Error with details if validation fails
 *
 * @example
 * ```ts
 * const mechanism = assertValidMechanism(someJsonData);
 * // mechanism is guaranteed to be a valid Mechanism here
 * ```
 */
export function assertValidMechanism(data: unknown): Mechanism {
  const result = validateMechanism(data);

  if (!result.success) {
    const firstError = result.errors[0];
    const path = firstError ? firstError.path.join(".") : "unknown";
    const message = firstError ? firstError.message : "Unknown validation error";
    throw new Error(`Invalid mechanism graph at ${path}: ${message}`);
  }

  return result.data;
}

/**
 * Parse a mechanism graph from a jsonb column, validating it.
 *
 * This is useful when reading from the database and you want to
 * ensure the stored data is valid.
 *
 * @param jsonbValue - The value from a jsonb column
 * @returns The validated mechanism
 * @throws Error if the data is invalid
 */
export function parseMechanismFromJsonb(jsonbValue: unknown): Mechanism {
  if (jsonbValue === null || jsonbValue === undefined) {
    throw new Error("Mechanism graph cannot be null or undefined");
  }

  return assertValidMechanism(jsonbValue);
}

/**
 * Prepare a mechanism graph for storage in a jsonb column.
 *
 * This validates the mechanism and returns it as a plain object
 * suitable for Drizzle's jsonb columns.
 *
 * @param mechanism - The mechanism to store
 * @returns The mechanism as a plain object
 * @throws Error if validation fails
 */
export function prepareMechanismForJsonb(mechanism: unknown): Mechanism {
  return assertValidMechanism(mechanism);
}
