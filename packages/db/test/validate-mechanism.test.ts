/**
 * Tests for mechanism graph validation helpers.
 */

import type { Mechanism } from "@orrery/schema";
import { describe, expect, it } from "vitest";
import {
  assertValidMechanism,
  parseMechanismFromJsonb,
  prepareMechanismForJsonb,
  validateMechanism,
} from "../src/validate-mechanism.ts";

describe("validateMechanism", () => {
  const validMechanism: Mechanism = {
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
    ],
    joints: [],
    drivers: [],
    provenance: {
      createdBy: "lab",
      footageIds: [],
    },
  };

  it("should validate a correct mechanism", () => {
    const result = validateMechanism(validMechanism);
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.id).toBe("test-mech");
    }
  });

  it("should reject an invalid mechanism", () => {
    const invalid = {
      ...validMechanism,
      schemaVersion: 2, // Invalid version
    };

    const result = validateMechanism(invalid);
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.errors.length).toBeGreaterThan(0);
      const firstError = result.errors[0];
      expect(firstError?.path).toContain("schemaVersion");
    }
  });

  it("should reject mechanism with missing required fields", () => {
    const invalid = {
      id: "test",
      name: "Test",
      // Missing schemaVersion and other required fields
    };

    const result = validateMechanism(invalid);
    expect(result.success).toBe(false);
  });

  it("should reject mechanism with dangling references", () => {
    const invalid: Mechanism = {
      ...validMechanism,
      bodies: [
        ...validMechanism.bodies,
        {
          id: "link1",
          label: "Link",
          kind: "link",
          planeId: "nonexistent-plane", // Dangling reference
          points: [],
          status: "observed",
          confidence: 0.9,
        },
      ],
    };

    const result = validateMechanism(invalid);
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.errors.some((e) => e.message.includes("non-existent plane"))).toBe(true);
    }
  });
});

describe("assertValidMechanism", () => {
  const validMechanism: Mechanism = {
    schemaVersion: 1,
    id: "test-mech",
    name: "Test",
    scale: { source: "unscaled", metersPerUnit: 1.0 },
    planes: [],
    bodies: [
      {
        id: "ground",
        label: "Ground",
        kind: "ground",
        planeId: null,
        points: [],
        status: "observed",
        confidence: 1.0,
      },
    ],
    joints: [],
    drivers: [],
    provenance: { createdBy: "user", footageIds: [] },
  };

  it("should return the mechanism if valid", () => {
    const result = assertValidMechanism(validMechanism);
    expect(result.id).toBe("test-mech");
  });

  it("should throw if the mechanism is invalid", () => {
    const invalid = { ...validMechanism, schemaVersion: "wrong" };
    expect(() => assertValidMechanism(invalid)).toThrow("Invalid mechanism graph");
  });
});

describe("parseMechanismFromJsonb", () => {
  const validMechanism: Mechanism = {
    schemaVersion: 1,
    id: "test",
    name: "Test",
    scale: { source: "unscaled", metersPerUnit: 1.0 },
    planes: [],
    bodies: [
      {
        id: "ground",
        label: "Ground",
        kind: "ground",
        planeId: null,
        points: [],
        status: "observed",
        confidence: 1.0,
      },
    ],
    joints: [],
    drivers: [],
    provenance: { createdBy: "user", footageIds: [] },
  };

  it("should parse valid jsonb data", () => {
    const result = parseMechanismFromJsonb(validMechanism);
    expect(result.id).toBe("test");
  });

  it("should throw on null", () => {
    expect(() => parseMechanismFromJsonb(null)).toThrow("cannot be null");
  });

  it("should throw on undefined", () => {
    expect(() => parseMechanismFromJsonb(undefined)).toThrow("cannot be null");
  });

  it("should throw on invalid data", () => {
    expect(() => parseMechanismFromJsonb({ invalid: true })).toThrow("Invalid mechanism graph");
  });
});

describe("prepareMechanismForJsonb", () => {
  const validMechanism: Mechanism = {
    schemaVersion: 1,
    id: "test",
    name: "Test",
    scale: { source: "unscaled", metersPerUnit: 1.0 },
    planes: [],
    bodies: [
      {
        id: "ground",
        label: "Ground",
        kind: "ground",
        planeId: null,
        points: [],
        status: "observed",
        confidence: 1.0,
      },
    ],
    joints: [],
    drivers: [],
    provenance: { createdBy: "user", footageIds: [] },
  };

  it("should prepare valid mechanism for storage", () => {
    const result = prepareMechanismForJsonb(validMechanism);
    expect(result.id).toBe("test");
    expect(result.schemaVersion).toBe(1);
  });

  it("should throw on invalid mechanism", () => {
    expect(() => prepareMechanismForJsonb({ invalid: true })).toThrow("Invalid mechanism graph");
  });
});
