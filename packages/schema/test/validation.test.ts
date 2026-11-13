/**
 * Tests for mechanism schema validation refinements.
 *
 * Validates the cross-cutting rules that Zod superRefine enforces:
 * - Reference integrity
 * - Single ground body
 * - No self-joints
 * - Type-specific requirements
 */
import { describe, expect, it } from "vitest";
import type { Mechanism } from "../src/mechanism.ts";
import { mechanismSchema } from "../src/mechanism.ts";

describe("Mechanism schema validation", () => {
  const validMinimalMechanism: Mechanism = {
    schemaVersion: 1,
    id: "test-mech",
    name: "Test Mechanism",
    scale: {
      source: "unscaled",
      metersPerUnit: 1.0,
    },
    planes: [
      {
        id: "plane1",
        originWorld: { x: 0, y: 0, z: 0 },
        normalWorld: { x: 0, y: 0, z: 1 },
        xAxisWorld: { x: 1, y: 0, z: 0 },
      },
    ],
    bodies: [
      {
        id: "ground",
        label: "Ground",
        kind: "ground",
        planeId: "plane1",
        points: [{ id: "p1", local: { x: 0, y: 0, z: 0 }, role: "joint_anchor" }],
        status: "observed",
        confidence: 1.0,
      },
      {
        id: "link1",
        label: "Link 1",
        kind: "link",
        planeId: "plane1",
        points: [
          { id: "p1", local: { x: 0, y: 0, z: 0 }, role: "joint_anchor" },
          { id: "p2", local: { x: 0.1, y: 0, z: 0 }, role: "joint_anchor" },
        ],
        status: "observed",
        confidence: 0.95,
      },
    ],
    joints: [
      {
        id: "j1",
        kind: "revolute",
        bodyA: "ground",
        bodyB: "link1",
        anchorA: { bodyId: "ground", pointId: "p1" },
        anchorB: { bodyId: "link1", pointId: "p1" },
        status: "observed",
        confidence: 0.9,
      },
    ],
    drivers: [
      {
        id: "d1",
        jointId: "j1",
        coordinate: "angle",
        profile: {
          type: "constant_rate",
          rate: 1.0,
          phase0: 0,
        },
      },
    ],
    provenance: {
      createdBy: "lab",
      footageIds: [],
    },
  };

  it("should accept a valid minimal mechanism", () => {
    const result = mechanismSchema.safeParse(validMinimalMechanism);
    expect(result.success).toBe(true);
  });

  it("should require exactly one ground body", () => {
    const noGround = {
      ...validMinimalMechanism,
      bodies: [
        {
          ...validMinimalMechanism.bodies[1],
          id: "link2",
        },
      ],
    };

    const result = mechanismSchema.safeParse(noGround);
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues.some((i) => i.message.includes("ground body"))).toBe(true);
    }
  });

  it("should reject multiple ground bodies", () => {
    const multiGround = {
      ...validMinimalMechanism,
      bodies: [
        ...validMinimalMechanism.bodies,
        {
          id: "ground2",
          label: "Ground 2",
          kind: "ground" as const,
          planeId: "plane1",
          points: [{ id: "p1", local: { x: 0, y: 0, z: 0 }, role: "joint_anchor" as const }],
          status: "observed" as const,
          confidence: 1.0,
        },
      ],
    };

    const result = mechanismSchema.safeParse(multiGround);
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues.some((i) => i.message.includes("exactly one ground body"))).toBe(
        true,
      );
    }
  });

  it("should reject duplicate body IDs", () => {
    const dupBodies = {
      ...validMinimalMechanism,
      bodies: [
        ...validMinimalMechanism.bodies,
        {
          ...validMinimalMechanism.bodies[1],
        },
      ],
    };

    const result = mechanismSchema.safeParse(dupBodies);
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues.some((i) => i.message.includes("Duplicate body IDs"))).toBe(true);
    }
  });

  it("should reject self-joints", () => {
    const selfJoint = {
      ...validMinimalMechanism,
      joints: [
        {
          id: "j1",
          kind: "revolute" as const,
          bodyA: "link1",
          bodyB: "link1",
          anchorA: { bodyId: "link1", pointId: "p1" },
          anchorB: { bodyId: "link1", pointId: "p2" },
          status: "observed" as const,
          confidence: 0.9,
        },
      ],
    };

    const result = mechanismSchema.safeParse(selfJoint);
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues.some((i) => i.message.includes("connects body"))).toBe(true);
    }
  });

  it("should reject dangling body references in joints", () => {
    const danglingBody = {
      ...validMinimalMechanism,
      joints: [
        {
          ...validMinimalMechanism.joints[0],
          bodyB: "nonexistent",
        },
      ],
    };

    const result = mechanismSchema.safeParse(danglingBody);
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues.some((i) => i.message.includes("non-existent body"))).toBe(true);
    }
  });

  it("should reject dangling point references", () => {
    const danglingPoint = {
      ...validMinimalMechanism,
      joints: [
        {
          ...validMinimalMechanism.joints[0],
          anchorB: { bodyId: "link1", pointId: "nonexistent" },
        },
      ],
    };

    const result = mechanismSchema.safeParse(danglingPoint);
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues.some((i) => i.message.includes("non-existent point"))).toBe(true);
    }
  });

  it("should reject dangling plane references", () => {
    const danglingPlane = {
      ...validMinimalMechanism,
      bodies: [
        ...validMinimalMechanism.bodies.slice(0, 1),
        {
          ...validMinimalMechanism.bodies[1],
          planeId: "nonexistent",
        },
      ],
    };

    const result = mechanismSchema.safeParse(danglingPlane);
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues.some((i) => i.message.includes("non-existent plane"))).toBe(true);
    }
  });

  it("should reject dangling joint references in drivers", () => {
    const danglingJoint = {
      ...validMinimalMechanism,
      drivers: [
        {
          ...validMinimalMechanism.drivers[0],
          jointId: "nonexistent",
        },
      ],
    };

    const result = mechanismSchema.safeParse(danglingJoint);
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues.some((i) => i.message.includes("non-existent joint"))).toBe(true);
    }
  });

  it("should require gear data for gear bodies", () => {
    const gearWithoutData = {
      ...validMinimalMechanism,
      bodies: [
        ...validMinimalMechanism.bodies,
        {
          id: "gear1",
          label: "Gear 1",
          kind: "gear" as const,
          planeId: "plane1",
          points: [{ id: "p1", local: { x: 0, y: 0, z: 0 }, role: "joint_anchor" as const }],
          status: "observed" as const,
          confidence: 0.9,
          // Missing gear data
        },
      ],
    };

    const result = mechanismSchema.safeParse(gearWithoutData);
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues.some((i) => i.message.includes("missing gear data"))).toBe(true);
    }
  });

  it("should require cam data for cam bodies", () => {
    const camWithoutData = {
      ...validMinimalMechanism,
      bodies: [
        ...validMinimalMechanism.bodies,
        {
          id: "cam1",
          label: "Cam 1",
          kind: "cam" as const,
          planeId: "plane1",
          points: [{ id: "p1", local: { x: 0, y: 0, z: 0 }, role: "joint_anchor" as const }],
          status: "observed" as const,
          confidence: 0.9,
          // Missing cam data
        },
      ],
    };

    const result = mechanismSchema.safeParse(camWithoutData);
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues.some((i) => i.message.includes("missing cam data"))).toBe(true);
    }
  });

  it("should require pulley data for pulley bodies", () => {
    const pulleyWithoutData = {
      ...validMinimalMechanism,
      bodies: [
        ...validMinimalMechanism.bodies,
        {
          id: "pulley1",
          label: "Pulley 1",
          kind: "pulley" as const,
          planeId: "plane1",
          points: [{ id: "p1", local: { x: 0, y: 0, z: 0 }, role: "joint_anchor" as const }],
          status: "observed" as const,
          confidence: 0.9,
          // Missing pulley data
        },
      ],
    };

    const result = mechanismSchema.safeParse(pulleyWithoutData);
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues.some((i) => i.message.includes("missing pulley data"))).toBe(true);
    }
  });

  it("should reject gear mesh between non-gear bodies", () => {
    const invalidGearMesh = {
      ...validMinimalMechanism,
      joints: [
        {
          id: "j1",
          kind: "gear_mesh" as const,
          bodyA: "ground",
          bodyB: "link1",
          ratio: -1.5,
          phase: 0,
          status: "inferred" as const,
          confidence: 0.8,
        },
      ],
    };

    const result = mechanismSchema.safeParse(invalidGearMesh);
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues.some((i) => i.message.includes("non-gear bodies"))).toBe(true);
    }
  });

  it("should reject belt between non-pulley bodies", () => {
    const invalidBelt = {
      ...validMinimalMechanism,
      joints: [
        {
          id: "j1",
          kind: "belt" as const,
          bodyA: "ground",
          bodyB: "link1",
          ratio: 2.0,
          crossed: false,
          status: "inferred" as const,
          confidence: 0.8,
        },
      ],
    };

    const result = mechanismSchema.safeParse(invalidBelt);
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues.some((i) => i.message.includes("non-pulley bodies"))).toBe(true);
    }
  });

  it("should reject roller cam follower without rollerRadius", () => {
    const camBody = {
      id: "cam1",
      label: "Cam",
      kind: "cam" as const,
      planeId: "plane1",
      points: [{ id: "p1", local: { x: 0, y: 0, z: 0 }, role: "joint_anchor" as const }],
      cam: {
        baseRadius: 0.05,
        fourier: { a: [0.01], b: [0.005] },
      },
      status: "observed" as const,
      confidence: 0.9,
    };

    const followerBody = {
      id: "follower1",
      label: "Follower",
      kind: "link" as const,
      planeId: "plane1",
      points: [{ id: "p1", local: { x: 0, y: 0, z: 0 }, role: "joint_anchor" as const }],
      status: "observed" as const,
      confidence: 0.9,
    };

    const invalidCamFollower = {
      ...validMinimalMechanism,
      bodies: [...validMinimalMechanism.bodies, camBody, followerBody],
      joints: [
        {
          id: "j1",
          kind: "cam_follower" as const,
          bodyA: "cam1",
          bodyB: "follower1",
          follower: "roller" as const,
          followerPoint: { bodyId: "follower1", pointId: "p1" },
          // Missing rollerRadius
          status: "inferred" as const,
          confidence: 0.8,
        },
      ],
    };

    const result = mechanismSchema.safeParse(invalidCamFollower);
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues.some((i) => i.message.includes("missing rollerRadius"))).toBe(
        true,
      );
    }
  });

  it("should reject mismatched array lengths in driver samples", () => {
    const mismatchedSamples = {
      ...validMinimalMechanism,
      drivers: [
        {
          id: "d1",
          jointId: "j1",
          coordinate: "angle" as const,
          profile: {
            type: "samples" as const,
            t: [0, 1, 2],
            q: [0, 0.5], // Length mismatch
          },
        },
      ],
    };

    const result = mechanismSchema.safeParse(mismatchedSamples);
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues.some((i) => i.message.includes("mismatched array lengths"))).toBe(
        true,
      );
    }
  });

  it("should reject planar joints between bodies in different planes", () => {
    const twoPlaneMech = {
      ...validMinimalMechanism,
      planes: [
        ...validMinimalMechanism.planes,
        {
          id: "plane2",
          originWorld: { x: 0, y: 0, z: 0.1 },
          normalWorld: { x: 0, y: 0, z: 1 },
          xAxisWorld: { x: 1, y: 0, z: 0 },
        },
      ],
      bodies: [
        ...validMinimalMechanism.bodies.slice(0, 1),
        { ...validMinimalMechanism.bodies[1], planeId: "plane2" },
      ],
    };

    const result = mechanismSchema.safeParse(twoPlaneMech);
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues.some((i) => i.message.includes("different planes"))).toBe(true);
    }
  });

  it("should accept valid gear bodies with gear mesh", () => {
    const gearMech: Mechanism = {
      schemaVersion: 1,
      id: "gear-test",
      name: "Gear Test",
      scale: { source: "unscaled", metersPerUnit: 1.0 },
      planes: [
        {
          id: "plane1",
          originWorld: { x: 0, y: 0, z: 0 },
          normalWorld: { x: 0, y: 0, z: 1 },
          xAxisWorld: { x: 1, y: 0, z: 0 },
        },
      ],
      bodies: [
        {
          id: "ground",
          label: "Ground",
          kind: "ground",
          planeId: "plane1",
          points: [],
          status: "observed",
          confidence: 1.0,
        },
        {
          id: "gear1",
          label: "Gear 1",
          kind: "gear",
          planeId: "plane1",
          points: [{ id: "center", local: { x: 0, y: 0, z: 0 }, role: "joint_anchor" }],
          gear: { teeth: 20, module: 0.003, internal: false },
          status: "observed",
          confidence: 0.9,
        },
        {
          id: "gear2",
          label: "Gear 2",
          kind: "gear",
          planeId: "plane1",
          points: [{ id: "center", local: { x: 0, y: 0, z: 0 }, role: "joint_anchor" }],
          gear: { teeth: 30, module: 0.003, internal: false },
          status: "observed",
          confidence: 0.9,
        },
      ],
      joints: [
        {
          id: "j1",
          kind: "gear_mesh",
          bodyA: "gear1",
          bodyB: "gear2",
          ratio: -1.5,
          phase: 0,
          status: "observed",
          confidence: 0.9,
        },
      ],
      drivers: [],
      provenance: {
        createdBy: "lab",
        footageIds: [],
      },
    };

    const result = mechanismSchema.safeParse(gearMech);
    expect(result.success).toBe(true);
  });
});
