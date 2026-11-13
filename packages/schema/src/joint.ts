/**
 * Joint schema: constraints between bodies.
 */
import { z } from "zod";
import {
  confidenceSchema,
  idSchema,
  pointRefSchema,
  statusSchema,
  vec2Schema,
  vec3Schema,
} from "./primitives.ts";

/** Curve types for pin-in-slot joints */
export const slotCurveSchema = z.discriminatedUnion("type", [
  z.object({
    type: z.literal("line_segment"),
    /** Start point in slot body's local frame (meters) */
    start: vec2Schema,
    /** End point in slot body's local frame (meters) */
    end: vec2Schema,
  }),
  z.object({
    type: z.literal("circular_arc"),
    /** Center in slot body's local frame (meters) */
    center: vec2Schema,
    /** Radius (meters) */
    radius: z.number().positive(),
    /** Start angle (radians) */
    angleStart: z.number().finite(),
    /** End angle (radians) */
    angleEnd: z.number().finite(),
  }),
  z.object({
    type: z.literal("cubic_bspline"),
    /** Control points in slot body's local frame (meters) */
    controlPoints: z.array(vec2Schema).min(4),
    /** Knot vector (parameter values) */
    knots: z.array(z.number().finite()),
  }),
]);

export type SlotCurve = z.infer<typeof slotCurveSchema>;

/** Cam follower types */
export const followerTypeSchema = z.enum(["knife", "roller", "flat"]);

export type FollowerType = z.infer<typeof followerTypeSchema>;

/** Base properties common to all joints */
const jointBaseSchema = z.object({
  /** Unique identifier */
  id: idSchema,

  /** First body (order matters for some joint types) */
  bodyA: idSchema,

  /** Second body */
  bodyB: idSchema,

  /** How this joint was determined */
  status: statusSchema,

  /** Confidence in this joint's existence and parameters (0 to 1) */
  confidence: confidenceSchema,
});

/** Planar revolute joint (pin joint) */
const revoluteJointSchema = jointBaseSchema.extend({
  kind: z.literal("revolute"),
  /** Anchor point on body A */
  anchorA: pointRefSchema,
  /** Anchor point on body B */
  anchorB: pointRefSchema,
  /** Optional axis for spatial revolute (omit for planar) */
  axisLocalA: vec3Schema.optional(),
});

/** Prismatic joint (slider) */
const prismaticJointSchema = jointBaseSchema.extend({
  kind: z.literal("prismatic"),
  /** Anchor point on body A */
  anchorA: pointRefSchema,
  /** Anchor point on body B */
  anchorB: pointRefSchema,
  /** Slide axis in body A's local frame (unit vector) */
  axisLocalA: vec3Schema,
  /** Optional displacement limits [min, max] in meters */
  limits: z.tuple([z.number().finite(), z.number().finite()]).optional(),
});

/** Pin-in-slot joint */
const pinInSlotJointSchema = jointBaseSchema.extend({
  kind: z.literal("pin_in_slot"),
  /** Pin point reference */
  pin: pointRefSchema,
  /** Slot curve in the slot body's frame */
  slot: slotCurveSchema,
});

/** Gear mesh constraint */
const gearMeshJointSchema = jointBaseSchema.extend({
  kind: z.literal("gear_mesh"),
  /** Gear ratio (teeth_B / teeth_A, negative for external mesh) */
  ratio: z.number().finite(),
  /** Phase offset (radians) */
  phase: z.number().finite(),
});

/** Belt or chain constraint */
const beltJointSchema = jointBaseSchema.extend({
  kind: z.literal("belt"),
  /** Pulley ratio */
  ratio: z.number().positive(),
  /** True for crossed belt, false for open belt */
  crossed: z.boolean(),
});

/** Cam-follower constraint */
const camFollowerJointSchema = jointBaseSchema.extend({
  kind: z.literal("cam_follower"),
  /** Follower type */
  follower: followerTypeSchema,
  /** Follower contact point */
  followerPoint: pointRefSchema,
  /** Roller radius (meters, required when follower is "roller") */
  rollerRadius: z.number().positive().optional(),
});

/** Linear spring */
const springJointSchema = jointBaseSchema.extend({
  kind: z.literal("spring"),
  /** Anchor point on body A */
  anchorA: pointRefSchema,
  /** Anchor point on body B */
  anchorB: pointRefSchema,
  /** Spring stiffness (N/m) */
  stiffness: z.number().positive(),
  /** Free length (meters) */
  freeLength: z.number().nonnegative(),
});

/** Spherical joint (ball joint) */
const sphericalJointSchema = jointBaseSchema.extend({
  kind: z.literal("spherical"),
  /** Anchor point on body A */
  anchorA: pointRefSchema,
  /** Anchor point on body B */
  anchorB: pointRefSchema,
});

/** Universal joint (Cardan joint) */
const universalJointSchema = jointBaseSchema.extend({
  kind: z.literal("universal"),
  /** Anchor point on body A */
  anchorA: pointRefSchema,
  /** Anchor point on body B */
  anchorB: pointRefSchema,
  /** Joint axes in local frames [axisA, axisB] */
  axesLocal: z.tuple([vec3Schema, vec3Schema]).optional(),
});

/** Cylindrical joint (prismatic + revolute about the same axis) */
const cylindricalJointSchema = jointBaseSchema.extend({
  kind: z.literal("cylindrical"),
  /** Anchor point on body A */
  anchorA: pointRefSchema,
  /** Anchor point on body B */
  anchorB: pointRefSchema,
  /** Cylinder axis in body A's local frame (unit vector) */
  axesLocal: z.tuple([vec3Schema, vec3Schema]).optional(),
});

/** Discriminated union of all joint types */
export const jointSchema = z.discriminatedUnion("kind", [
  revoluteJointSchema,
  prismaticJointSchema,
  pinInSlotJointSchema,
  gearMeshJointSchema,
  beltJointSchema,
  camFollowerJointSchema,
  springJointSchema,
  sphericalJointSchema,
  universalJointSchema,
  cylindricalJointSchema,
]);

export type Joint = z.infer<typeof jointSchema>;
