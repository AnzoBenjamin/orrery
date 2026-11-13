/**
 * Primitive geometric types for the mechanism schema.
 * All coordinates and distances are in SI units (meters, radians).
 */
import { z } from "zod";

/** 2D vector in meters */
export const vec2Schema = z
  .object({
    x: z.number().finite(),
    y: z.number().finite(),
  })
  .meta({ id: "Vec2" });

export type Vec2 = z.infer<typeof vec2Schema>;

/** 3D vector in meters */
export const vec3Schema = z
  .object({
    x: z.number().finite(),
    y: z.number().finite(),
    z: z.number().finite(),
  })
  .meta({ id: "Vec3" });

export type Vec3 = z.infer<typeof vec3Schema>;

/** Status of an element: how it was created or identified */
export const statusSchema = z
  .enum(["observed", "inferred", "user", "candidate"])
  .meta({ id: "Status" });

export type Status = z.infer<typeof statusSchema>;

/** Confidence value between 0 and 1 */
export const confidenceSchema = z.number().min(0).max(1);

/** String identifier (non-empty) */
export const idSchema = z.string().min(1);

/** Point reference within a body */
export const pointRefSchema = z
  .object({
    bodyId: idSchema,
    pointId: idSchema,
  })
  .meta({ id: "PointRef" });

export type PointRef = z.infer<typeof pointRefSchema>;
