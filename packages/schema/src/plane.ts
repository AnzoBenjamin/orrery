/**
 * Plane schema: a 2D coordinate system embedded in 3D world space.
 */
import { z } from "zod";
import { idSchema, vec3Schema } from "./primitives.ts";

export const planeSchema = z.object({
  /** Unique identifier for this plane */
  id: idSchema,

  /** Origin point in world coordinates (meters) */
  originWorld: vec3Schema,

  /** Plane normal vector in world coordinates (unit vector) */
  normalWorld: vec3Schema,

  /** X-axis direction in world coordinates (unit vector, perpendicular to normal) */
  xAxisWorld: vec3Schema,
});

export type Plane = z.infer<typeof planeSchema>;
