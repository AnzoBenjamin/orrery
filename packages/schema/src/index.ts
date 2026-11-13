/**
 * Mechanism graph schema for Orrery.
 *
 * This is the single source of truth for mechanism representation.
 * Types are generated for Rust (via JSON Schema and typify) and Python
 * (via JSON Schema and datamodel-code-generator).
 *
 * All geometry is in SI units: meters for distances, radians for angles.
 */

export * from "./body.ts";
export * from "./driver.ts";
export * from "./joint.ts";
export * from "./mechanism.ts";
// Re-export the main schema as the default
export { mechanismSchema as default } from "./mechanism.ts";
export * from "./migrations.ts";
export * from "./plane.ts";
// Export all schemas and types
export * from "./primitives.ts";
