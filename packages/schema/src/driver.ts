/**
 * Driver schema: inputs that set joint coordinates over time.
 */
import { z } from "zod";
import { idSchema } from "./primitives.ts";

/** Coordinate type being driven */
export const driverCoordinateSchema = z
  .enum(["angle", "displacement"])
  .meta({ id: "DriverCoordinate" });

export type DriverCoordinate = z.infer<typeof driverCoordinateSchema>;

/** Driver profile types */
const constantRateProfileSchema = z
  .object({
    type: z.literal("constant_rate"),
    /** Rate of change (rad/s or m/s) */
    rate: z.number().finite(),
    /** Initial phase at t=0 */
    phase0: z.number().finite(),
  })
  .meta({ title: "ConstantRateProfile" });

const samplesProfileSchema = z
  .object({
    type: z.literal("samples"),
    /** Time samples (seconds) */
    t: z.array(z.number().finite()).min(2),
    /** Coordinate values at each time sample */
    q: z.array(z.number().finite()).min(2),
  })
  .meta({ title: "SamplesProfile" });

const driverProfileSchema = z
  .discriminatedUnion("type", [constantRateProfileSchema, samplesProfileSchema])
  .meta({ id: "DriverProfile" });

export type DriverProfile = z.infer<typeof driverProfileSchema>;

/** A driver that sets a joint coordinate over time */
export const driverSchema = z
  .object({
    /** Unique identifier */
    id: idSchema,

    /** Joint being driven */
    jointId: idSchema,

    /** Which coordinate of the joint is driven */
    coordinate: driverCoordinateSchema,

    /** Time profile */
    profile: driverProfileSchema,
  })
  .meta({ id: "Driver" });

export type Driver = z.infer<typeof driverSchema>;
