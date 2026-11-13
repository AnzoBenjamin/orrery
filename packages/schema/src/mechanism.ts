/**
 * Complete mechanism graph schema with validation refinements.
 */
import { z } from "zod";
import { type Body, bodySchema } from "./body.ts";
import { driverSchema } from "./driver.ts";
import { jointSchema } from "./joint.ts";
import { planeSchema } from "./plane.ts";
import { idSchema } from "./primitives.ts";

/** How scale was established */
export const scaleSourceSchema = z.enum([
  "user_measurement",
  "reference_object",
  "intrinsics",
  "unscaled",
]);

export type ScaleSource = z.infer<typeof scaleSourceSchema>;

/** Scale information */
export const scaleSchema = z.object({
  /** Method used to establish scale */
  source: scaleSourceSchema,

  /** Conversion factor from mechanism units to meters */
  metersPerUnit: z.number().positive(),

  /** Optional standard deviation of scale estimate (meters) */
  sigma: z.number().nonnegative().optional(),
});

export type Scale = z.infer<typeof scaleSchema>;

/** Provenance: how this mechanism was created */
export const provenanceSchema = z.object({
  /** Creator */
  createdBy: z.enum(["engine", "user", "lab"]),

  /** Optional analysis run ID */
  analysisId: idSchema.optional(),

  /** Source footage IDs */
  footageIds: z.array(idSchema),

  /** Engine version that created this (semantic version) */
  engineVersion: z.string().optional(),
});

export type Provenance = z.infer<typeof provenanceSchema>;

/** Parameter path for uncertainty mapping */
export type ParameterPath = string;

/** Uncertainty as standard deviations keyed by parameter path */
export const uncertaintySchema = z.record(z.string(), z.number().nonnegative());

export type Uncertainty = z.infer<typeof uncertaintySchema>;

/** Complete mechanism graph */
export const mechanismSchemaBase = z.object({
  /** Schema version for forward compatibility */
  schemaVersion: z.literal(1),

  /** Unique identifier for this mechanism */
  id: idSchema,

  /** Human-readable name */
  name: z.string(),

  /** Scale information */
  scale: scaleSchema,

  /** Planes for planar subsystems */
  planes: z.array(planeSchema),

  /** Bodies in the mechanism */
  bodies: z.array(bodySchema),

  /** Joints connecting bodies */
  joints: z.array(jointSchema),

  /** Drivers (inputs) */
  drivers: z.array(driverSchema),

  /** Provenance information */
  provenance: provenanceSchema,

  /** Optional parameter uncertainties */
  uncertainty: uncertaintySchema.optional(),
});

/**
 * Mechanism schema with validation refinements.
 *
 * Validates:
 * - Reference integrity (all IDs referenced exist)
 * - Single ground body
 * - No self-joints (body connected to itself)
 * - Planar joints only between bodies in the same plane
 * - Gear joints only between gear bodies
 * - Required type-specific data present
 */
export const mechanismSchema = mechanismSchemaBase.superRefine((mechanism, ctx) => {
  const bodyIds = new Set(mechanism.bodies.map((b) => b.id));
  const jointIds = new Set(mechanism.joints.map((j) => j.id));
  const planeIds = new Set(mechanism.planes.map((p) => p.id));

  // Check for duplicate IDs
  if (bodyIds.size !== mechanism.bodies.length) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      message: "Duplicate body IDs found",
      path: ["bodies"],
    });
  }

  if (jointIds.size !== mechanism.joints.length) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      message: "Duplicate joint IDs found",
      path: ["joints"],
    });
  }

  if (planeIds.size !== mechanism.planes.length) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      message: "Duplicate plane IDs found",
      path: ["planes"],
    });
  }

  // Check single ground body
  const groundBodies = mechanism.bodies.filter((b) => b.kind === "ground");
  if (groundBodies.length === 0) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      message: "Mechanism must have exactly one ground body",
      path: ["bodies"],
    });
  } else if (groundBodies.length > 1) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      message: `Mechanism must have exactly one ground body, found ${groundBodies.length}`,
      path: ["bodies"],
    });
  }

  // Build body lookup and point lookup
  const bodyMap = new Map<string, Body>(mechanism.bodies.map((b) => [b.id, b]));
  const pointMap = new Map<string, Set<string>>();

  for (const body of mechanism.bodies) {
    const points = new Set(body.points.map((p) => p.id));
    if (points.size !== body.points.length) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: `Body ${body.id} has duplicate point IDs`,
        path: ["bodies"],
      });
    }
    pointMap.set(body.id, points);

    // Check plane reference
    if (body.planeId !== null && !planeIds.has(body.planeId)) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: `Body ${body.id} references non-existent plane ${body.planeId}`,
        path: ["bodies"],
      });
    }

    // Check required type-specific data
    if (body.kind === "gear" && !body.gear) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: `Body ${body.id} is a gear but missing gear data`,
        path: ["bodies"],
      });
    }
    if (body.kind === "cam" && !body.cam) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: `Body ${body.id} is a cam but missing cam data`,
        path: ["bodies"],
      });
    }
    if (body.kind === "pulley" && !body.pulley) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: `Body ${body.id} is a pulley but missing pulley data`,
        path: ["bodies"],
      });
    }
  }

  // Validate joints
  for (let i = 0; i < mechanism.joints.length; i++) {
    const joint = mechanism.joints[i];
    if (!joint) continue;

    // Check body references
    if (!bodyIds.has(joint.bodyA)) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: `Joint ${joint.id} references non-existent body ${joint.bodyA}`,
        path: ["joints", i, "bodyA"],
      });
    }
    if (!bodyIds.has(joint.bodyB)) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: `Joint ${joint.id} references non-existent body ${joint.bodyB}`,
        path: ["joints", i, "bodyB"],
      });
    }

    // Check for self-joints
    if (joint.bodyA === joint.bodyB) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: `Joint ${joint.id} connects body ${joint.bodyA} to itself`,
        path: ["joints", i],
      });
    }

    const bodyA = bodyMap.get(joint.bodyA);
    const bodyB = bodyMap.get(joint.bodyB);

    if (bodyA && bodyB) {
      // Check planar constraint consistency
      const planarJointKinds = [
        "revolute",
        "prismatic",
        "pin_in_slot",
        "gear_mesh",
        "belt",
        "cam_follower",
        "spring",
      ];

      if (planarJointKinds.includes(joint.kind)) {
        // Both bodies must be in the same plane or at least one must be spatial
        if (bodyA.planeId !== null && bodyB.planeId !== null && bodyA.planeId !== bodyB.planeId) {
          ctx.addIssue({
            code: z.ZodIssueCode.custom,
            message: `Planar joint ${joint.id} connects bodies in different planes (${bodyA.planeId} and ${bodyB.planeId})`,
            path: ["joints", i],
          });
        }
      }

      // Gear mesh validation
      if (joint.kind === "gear_mesh") {
        if (bodyA.kind !== "gear" || bodyB.kind !== "gear") {
          ctx.addIssue({
            code: z.ZodIssueCode.custom,
            message: `Gear mesh joint ${joint.id} connects non-gear bodies`,
            path: ["joints", i],
          });
        }
      }

      // Belt validation
      if (joint.kind === "belt") {
        if (bodyA.kind !== "pulley" || bodyB.kind !== "pulley") {
          ctx.addIssue({
            code: z.ZodIssueCode.custom,
            message: `Belt joint ${joint.id} connects non-pulley bodies`,
            path: ["joints", i],
          });
        }
      }

      // Cam follower validation
      if (joint.kind === "cam_follower") {
        const camBody = bodyA.kind === "cam" ? bodyA : bodyB.kind === "cam" ? bodyB : null;
        if (!camBody) {
          ctx.addIssue({
            code: z.ZodIssueCode.custom,
            message: `Cam follower joint ${joint.id} does not connect a cam body`,
            path: ["joints", i],
          });
        }

        if (joint.follower === "roller" && !joint.rollerRadius) {
          ctx.addIssue({
            code: z.ZodIssueCode.custom,
            message: `Cam follower joint ${joint.id} with roller follower missing rollerRadius`,
            path: ["joints", i],
          });
        }
      }
    }

    // Validate point references for joints with anchors
    const validatePointRef = (ref: { bodyId: string; pointId: string }, fieldName: string) => {
      if (!bodyIds.has(ref.bodyId)) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: `Joint ${joint.id} ${fieldName} references non-existent body ${ref.bodyId}`,
          path: ["joints", i, fieldName],
        });
      } else {
        const points = pointMap.get(ref.bodyId);
        if (points && !points.has(ref.pointId)) {
          ctx.addIssue({
            code: z.ZodIssueCode.custom,
            message: `Joint ${joint.id} ${fieldName} references non-existent point ${ref.pointId} on body ${ref.bodyId}`,
            path: ["joints", i, fieldName],
          });
        }
      }
    };

    if ("anchorA" in joint && joint.anchorA) {
      validatePointRef(joint.anchorA, "anchorA");
    }
    if ("anchorB" in joint && joint.anchorB) {
      validatePointRef(joint.anchorB, "anchorB");
    }
    if ("pin" in joint && joint.pin) {
      validatePointRef(joint.pin, "pin");
    }
    if ("followerPoint" in joint && joint.followerPoint) {
      validatePointRef(joint.followerPoint, "followerPoint");
    }
  }

  // Validate drivers
  for (let i = 0; i < mechanism.drivers.length; i++) {
    const driver = mechanism.drivers[i];
    if (!driver) continue;

    if (!jointIds.has(driver.jointId)) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: `Driver ${driver.id} references non-existent joint ${driver.jointId}`,
        path: ["drivers", i, "jointId"],
      });
    }

    // Validate samples profile
    if (driver.profile.type === "samples") {
      if (driver.profile.t.length !== driver.profile.q.length) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: `Driver ${driver.id} samples profile has mismatched array lengths`,
          path: ["drivers", i, "profile"],
        });
      }
    }
  }
});

export type Mechanism = z.infer<typeof mechanismSchema>;
