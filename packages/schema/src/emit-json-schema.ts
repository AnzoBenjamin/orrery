/**
 * `pnpm codegen` for the mechanism graph: Zod → JSON Schema (schema/mechanism.json).
 * Rust types (typify) and Python models (datamodel-code-generator) are generated from that file.
 *
 * The structural schema is emitted. Cross-reference rules in `mechanismSchema`'s refinement
 * (dangling ids, ground body, driver targets) cannot be expressed in JSON Schema, so every
 * consumer validates through the shared solver or the Zod schema as well.
 */
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { z } from "zod";
import { mechanismSchemaBase } from "./mechanism.ts";

const outputPath = join(dirname(fileURLToPath(import.meta.url)), "..", "schema", "mechanism.json");

const { $schema: _drop, ...emitted } = z.toJSONSchema(mechanismSchemaBase, {
  target: "draft-2020-12",
  io: "input",
}) as Record<string, unknown>;

const document = {
  $schema: "https://json-schema.org/draft/2020-12/schema",
  title: "Mechanism",
  description: "Orrery mechanism graph. Generated from packages/schema; do not edit.",
  ...emitted,
};

mkdirSync(dirname(outputPath), { recursive: true });
writeFileSync(outputPath, `${JSON.stringify(document, null, 2)}\n`);
