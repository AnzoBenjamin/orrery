/**
 * Body schema: rigid or compliant parts in a mechanism.
 */
import { z } from "zod";
import { confidenceSchema, idSchema, statusSchema, vec2Schema, vec3Schema } from "./primitives.ts";

/** Body kinds supported by the solver */
export const bodyKindSchema = z
  .enum(["ground", "link", "slider_block", "gear", "cam", "pulley", "compliant"])
  .meta({ id: "BodyKind" });

export type BodyKind = z.infer<typeof bodyKindSchema>;

/** Role of a point on a body */
export const pointRoleSchema = z
  .enum(["joint_anchor", "tracked", "output", "hole"])
  .meta({ id: "PointRole" });

export type PointRole = z.infer<typeof pointRoleSchema>;

/** A named point on a body in its local coordinate frame */
export const bodyPointSchema = z
  .object({
    /** Unique identifier within this body */
    id: idSchema,

    /** Point coordinates in the body's local frame (meters) */
    local: vec3Schema,

    /** Purpose of this point */
    role: pointRoleSchema,
  })
  .meta({ id: "BodyPoint" });

export type BodyPoint = z.infer<typeof bodyPointSchema>;

/** Body outline for collision detection */
export const outlineSchema = z
  .object({
    /** Polygon vertices in the body's local 2D frame (planar bodies only) */
    polygonLocal: z.array(vec2Schema).min(3),

    /** Thickness perpendicular to the plane (meters) */
    thickness: z.number().positive(),
  })
  .meta({ id: "Outline" });

export type Outline = z.infer<typeof outlineSchema>;

/** Gear-specific data */
export const gearDataSchema = z
  .object({
    /** Number of teeth */
    teeth: z.number().int().positive(),

    /** Module in meters (pitch diameter / teeth) */
    module: z.number().positive(),

    /** True for internal (ring) gears, false for external (spur/pinion) */
    internal: z.boolean(),
  })
  .meta({ id: "GearData" });

export type GearData = z.infer<typeof gearDataSchema>;

/** Cam profile as a Fourier series: r(θ) = baseRadius + Σ(a_n cos(nθ) + b_n sin(nθ)) */
export const camDataSchema = z
  .object({
    /** Base radius in meters */
    baseRadius: z.number().positive(),

    /** Fourier coefficients for the radial profile */
    fourier: z.object({
      /** Cosine coefficients (a[0] is DC offset) */
      a: z.array(z.number().finite()),

      /** Sine coefficients */
      b: z.array(z.number().finite()),
    }),
  })
  .meta({ id: "CamData" });

export type CamData = z.infer<typeof camDataSchema>;

/** Pulley-specific data */
export const pulleyDataSchema = z
  .object({
    /** Pulley radius in meters */
    radius: z.number().positive(),
  })
  .meta({ id: "PulleyData" });

export type PulleyData = z.infer<typeof pulleyDataSchema>;

/** A rigid or compliant body in the mechanism */
export const bodySchema = z
  .object({
    /** Unique identifier */
    id: idSchema,

    /** Human-readable label (e.g., "A", "crank", "follower") */
    label: z.string(),

    /** Body type */
    kind: bodyKindSchema,

    /** Plane this body is constrained to, or null for spatial bodies */
    planeId: idSchema.nullable(),

    /** Named points in the body's local frame */
    points: z.array(bodyPointSchema),

    /** Optional outline for collision detection (planar bodies only) */
    outline: outlineSchema.optional(),

    /** Gear-specific data (required when kind is "gear") */
    gear: gearDataSchema.optional(),

    /** Cam-specific data (required when kind is "cam") */
    cam: camDataSchema.optional(),

    /** Pulley-specific data (required when kind is "pulley") */
    pulley: pulleyDataSchema.optional(),

    /** How this body was determined */
    status: statusSchema,

    /** Confidence in this body's existence and parameters (0 to 1) */
    confidence: confidenceSchema,
  })
  .meta({ id: "Body" });

export type Body = z.infer<typeof bodySchema>;
