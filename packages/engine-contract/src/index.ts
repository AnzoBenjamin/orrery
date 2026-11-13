/**
 * The worker ↔ engine contract (design: "Engine contract"). Zod is the source of truth: it emits
 * JSON Schema (schema/engine-contract.json), from which the engine's Pydantic models are
 * generated. Both are committed, and `pnpm check` fails when they are out of date.
 */

export {
  type ProbeRequest,
  type ProbeResponse,
  probeAccepted,
  probeRejected,
  probeRequest,
  probeResponse,
} from "./probe.ts";
export { CONTRACT_VERSION, contractSchemas } from "./schemas.ts";
