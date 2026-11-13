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
export const slotCurveSchema = z
  .discriminatedUnion("type", [
    z
      .object({
        type: z.literal("line_segment"),
        /** Start point in slot body's local frame (meters) */
        start: vec2Schema,
        /** End point in slot body's local frame (meters) */
        end: vec2Schema,
      })
      .meta({ title: "LineSegmentSlot" }),
    z
      .object({
        type: z.literal("circular_arc"),
        /** Center in slot body's local frame (meters) */
        center: vec2Schema,
        /** Radius (meters) */
        radius: z.number().positive(),
        /** Start angle (radians) */
        angleStart: z.number().finite(),
        /** End angle (radians) */
        angleEnd: z.number().finite(),
      })
      .meta({ title: "CircularArcSlot" }),
    z
      .object({
        type: z.literal("cubic_bspline"),
        /** Control points in slot body's local frame (meters) */
        controlPoints: z.array(vec2Schema).min(4),
        /** Knot vector (parameter values) */
        knots: z.array(z.number().finite()),
      })
      .meta({ title: "CubicBsplineSlot" }),
  ])
  .meta({ id: "SlotCurve" });

export type SlotCurve = z.infer<typeof slotCurveSchema>;

/** Cam follower types */
export const followerTypeSchema = z.enum(["knife", "roller", "flat"]).meta({ id: "FollowerType" });

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
const revoluteJointSchema = jointBaseSchema
  .extend({
    kind: z.literal("revolute"),
    /** Anchor point on body A */
    anchorA: pointRefSchema,
    /** Anchor point on body B */
    anchorB: pointRefSchema,
    /**
     * Turning axis in A's frame, required when either body is spatial (omit for planar). B turns
     * about the same local vector in its own frame.
     */
    axisLocalA: vec3Schema.optional(),
  })
  .meta({ title: "RevoluteJoint" });

/**
 * Prismatic joint (slider). B's anchor stays on the line through A's anchor along `axisLocalA`,
 * and B keeps A's orientation: B's local frame is parallel to A's, so draw slider frames that way.
 */
const prismaticJointSchema = jointBaseSchema
  .extend({
    kind: z.literal("prismatic"),
    /** Anchor point on body A */
    anchorA: pointRefSchema,
    /** Anchor point on body B */
    anchorB: pointRefSchema,
    /** Slide axis in body A's local frame (unit vector) */
    axisLocalA: vec3Schema,
    /** Optional displacement limits [min, max] in meters */
    limits: z.tuple([z.number().finite(), z.number().finite()]).optional(),
  })
  .meta({ title: "PrismaticJoint" });

/**
 * Pin-in-slot joint. The pin is on `pin.bodyId`; the slot is cut in the joint's other body. A pose
 * with the pin past either end of the slot is not an assembly.
 */
const pinInSlotJointSchema = jointBaseSchema
  .extend({
    kind: z.literal("pin_in_slot"),
    /** Pin point reference */
    pin: pointRefSchema,
    /** Slot curve in the slot body's frame */
    slot: slotCurveSchema,
  })
  .meta({ title: "PinInSlotJoint" });

/**
 * Gear mesh: (θA − θC) = ratio · (θB − θC) + phase, angles relative to the carrier C, the body both
 * gears are pinned to by revolute joints (the ground for fixed axles, the arm of a planetary set).
 */
const gearMeshJointSchema = jointBaseSchema
  .extend({
    kind: z.literal("gear_mesh"),
    /** Gear ratio (teeth_B / teeth_A, negative for external mesh) */
    ratio: z.number().finite(),
    /** Phase offset (radians) */
    phase: z.number().finite(),
  })
  .meta({ title: "GearMeshJoint" });

/** Belt or chain between two pulleys pinned to one carrier, like a gear mesh with zero phase. */
const beltJointSchema = jointBaseSchema
  .extend({
    kind: z.literal("belt"),
    /** Radius of B over radius of A, so A turns `ratio` times as far as B */
    ratio: z.number().positive(),
    /** True for crossed belt, false for open belt */
    crossed: z.boolean(),
  })
  .meta({ title: "BeltJoint" });

/**
 * Cam-follower contact. A knife edge touches the profile at `followerPoint`, a roller centered there
 * rolls on it, and a flat face through `followerPoint` along the follower's local x axis rests on it.
 */
const camFollowerJointSchema = jointBaseSchema
  .extend({
    kind: z.literal("cam_follower"),
    /** Follower type */
    follower: followerTypeSchema,
    /** Follower contact point */
    followerPoint: pointRefSchema,
    /** Roller radius (meters, required when follower is "roller") */
    rollerRadius: z.number().positive().optional(),
  })
  .meta({ title: "CamFollowerJoint" });

/** Linear spring */
const springJointSchema = jointBaseSchema
  .extend({
    kind: z.literal("spring"),
    /** Anchor point on body A */
    anchorA: pointRefSchema,
    /** Anchor point on body B */
    anchorB: pointRefSchema,
    /** Spring stiffness (N/m) */
    stiffness: z.number().positive(),
    /** Free length (meters) */
    freeLength: z.number().nonnegative(),
  })
  .meta({ title: "SpringJoint" });

/** Spherical joint (ball joint) */
const sphericalJointSchema = jointBaseSchema
  .extend({
    kind: z.literal("spherical"),
    /** Anchor point on body A */
    anchorA: pointRefSchema,
    /** Anchor point on body B */
    anchorB: pointRefSchema,
  })
  .meta({ title: "SphericalJoint" });

/** Universal joint (Cardan joint) */
const universalJointSchema = jointBaseSchema
  .extend({
    kind: z.literal("universal"),
    /** Anchor point on body A */
    anchorA: pointRefSchema,
    /** Anchor point on body B */
    anchorB: pointRefSchema,
    /** The two cross arms: A's in A's frame, B's in B's frame. They stay perpendicular. */
    axesLocal: z.tuple([vec3Schema, vec3Schema]).optional(),
  })
  .meta({ title: "UniversalJoint" });

/** Cylindrical joint (prismatic + revolute about the same axis) */
const cylindricalJointSchema = jointBaseSchema
  .extend({
    kind: z.literal("cylindrical"),
    /** Anchor point on body A */
    anchorA: pointRefSchema,
    /** Anchor point on body B */
    anchorB: pointRefSchema,
    /** The cylinder axis in A's frame and in B's frame. B's anchor stays on A's axis line. */
    axesLocal: z.tuple([vec3Schema, vec3Schema]).optional(),
  })
  .meta({ title: "CylindricalJoint" });

/** Discriminated union of all joint types */
export const jointSchema = z
  .discriminatedUnion("kind", [
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
  ])
  .meta({ id: "Joint" });

export type Joint = z.infer<typeof jointSchema>;
